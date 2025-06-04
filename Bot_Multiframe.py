from datetime import datetime, timedelta, timezone
import ccxt
import sys
import time
import os
import pandas as pd
import pandas_ta as ta
import pygame
import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView, QSplitter
)

COLORS = {
    "verde": "\033[92m",
    "rojo": "\033[91m",
    "reset": "\033[0m",
    "azul": "\033[94m",
    "amarillo": "\033[93m"
}

def format_utc_to_local(utc_dt):
    try:
        if pd.isna(utc_dt):
            return "Invalid date"
        if isinstance(utc_dt, str):
            utc_dt = pd.to_datetime(utc_dt)
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        return utc_dt.strftime('%H:%M:%S')  # Solo hora UTC
    except Exception as e:
        return "Hora inválida"

class CryptoMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.exchange = ccxt.mexc()
        self.coins = [
            "ADA/USDT:USDT", "APT/USDT:USDT", "CRO/USDT:USDT", "DOGE/USDT:USDT", "DOT/USDT:USDT",
            "HBAR/USDT:USDT", "KAS/USDT:USDT", "NEAR/USDT:USDT", "ONDO/USDT:USDT", "PEPE/USDT:USDT",
            "PI/USDT:USDT", "POL/USDT:USDT", "SHIB/USDT:USDT", "SUI/USDT:USDT", "TONCOIN/USDT:USDT",
            "TRX/USDT:USDT", "VET/USDT:USDT", "WLD/USDT:USDT", "XLM/USDT:USDT", "XRP/USDT:USDT"
        ]
        self.previous_trends = {coin: None for coin in self.coins}
        self.hourly_data = {coin: None for coin in self.coins}
        self.last_hourly_update = None
        self.timers = {}

        pygame.init()
        pygame.mixer.init()

        self.setup_ui()
        print(f"{COLORS['azul']}🔄 Cargando datos horarios iniciales...{COLORS['reset']}")
        self.update_hourly_data()
        self.setup_timers()
        QTimer.singleShot(1000, lambda: self.update_timeframe_data("Min15"))

    def reset_exchange(self):
        try:
            self.exchange = ccxt.mexc()
            print(f"{COLORS['azul']}🔄 Exchange reiniciado{COLORS['reset']}")
        except Exception as e:
            print(f"{COLORS['rojo']}Error reiniciando exchange: {str(e)}{COLORS['reset']}")

    def setup_ui(self):
        self.setWindowTitle("Monitor Futuros")
        self.setGeometry(100, 100, 600, 1200)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter)

        self.monitoring_table = QTableWidget()
        self.setup_monitoring_table()
        self.initialize_table_data()
        splitter.addWidget(self.monitoring_table)

        self.alert_log = QTableWidget()
        self.setup_alert_log()
        splitter.addWidget(self.alert_log)

        self.close_button = QPushButton("Cerrar Programa")
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)

    def setup_monitoring_table(self):
        headers = ["Moneda", "EMA21(15m)", "EMA50(1h)", "Tendencia"]
        self.monitoring_table.setColumnCount(len(headers))
        self.monitoring_table.setHorizontalHeaderLabels(headers)

        self.monitoring_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def setup_alert_log(self):
        headers = ["", "Hora", "Moneda", "Mensaje"]
        self.alert_log.setColumnCount(len(headers))
        self.alert_log.setHorizontalHeaderLabels(headers)
        self.alert_log.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    def initialize_table_data(self):
        self.monitoring_table.setRowCount(len(self.coins))
        for row, coin in enumerate(self.coins):
            self.monitoring_table.setItem(row, 0, QTableWidgetItem(coin))
            for col in range(1, 4):
                self.monitoring_table.setItem(row, col, QTableWidgetItem("Cargando..."))

        self.monitoring_table.resizeColumnsToContents()

    def update_hourly_data(self):
        now = datetime.now(timezone.utc)
        if self.last_hourly_update is None or (now - self.last_hourly_update).total_seconds() >= 3600:
            print(f"{COLORS['azul']}🔄 Actualizando datos horarios{COLORS['reset']}")
            for coin in self.coins:
                df = self.fetch_historical_data(coin, "Min60")
                if df is not None:
                    self.hourly_data[coin] = df
                    print(f"{COLORS['verde']}✅ Datos horarios actualizados para {coin}{COLORS['reset']}")
                else:
                    print(f"{COLORS['rojo']}❌ Error actualizando datos horarios para {coin}{COLORS['reset']}")
            self.last_hourly_update = now

    def fetch_historical_data(self, symbol, interval, retry_count=3):
        timeframe_map = {"Min15": "15m", "Min60": "1h"}
        timeframe = timeframe_map[interval]

        for attempt in range(retry_count):
            try:
                print(
                    f"{COLORS['azul']}🔄 Intentando descargar {symbol} ({interval}) - Intento {attempt + 1}{COLORS['reset']}")
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=300)
                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)


                if df.empty or len(df) < 2:
                    print(f"{COLORS['rojo']}❌ No hay suficientes datos para {symbol} ({interval}){COLORS['reset']}")
                    return None

                df = df.sort_values("timestamp").reset_index(drop=True)
                last_candle_time = df["timestamp"].iloc[-2]
                print(
                    f"{COLORS['verde']}✅ {symbol} ({interval}) procesado correctamente - Última vela cerrada (UTC): {format_utc_to_local(last_candle_time)}{COLORS['reset']}")
                return df.iloc[:-1]

            except Exception as e:
                print(
                    f"{COLORS['rojo']}Error en {symbol} ({interval}): {str(e)} - Intento {attempt + 1}{COLORS['reset']}")
                if attempt < retry_count - 1:
                    self.reset_exchange()
                    time.sleep(2)

        return None

    def calculate_indicators(self, df, timeframe):
        try:
            df = df.dropna(subset=["close"])
            if timeframe == "Min15":
                if len(df) < 210:
                    return "Error"
                ema = ta.ema(df["close"], length=21)
            else:
                if len(df) < 60:
                    return "Error"
                ema = ta.ema(df["close"], length=50)

            if pd.isna(ema.iloc[-1]):
                return "Error"
            return "Alcista" if df["close"].iloc[-1] > ema.iloc[-1] else "Bajista"
        except Exception as e:
            print(f"Error calculando indicador: {str(e)}")
            return "Error"

    def update_row(self, row):
        coin = self.coins[row]
        self.monitoring_table.setItem(row, 0, QTableWidgetItem(coin))

        df_15m = self.fetch_historical_data(coin, "Min15")
        state_15m = self.calculate_indicators(df_15m, "Min15") if df_15m is not None else "Error"
        self.monitoring_table.setItem(row, 1, QTableWidgetItem(state_15m))

        df_1h = self.hourly_data.get(coin)
        state_1h = self.calculate_indicators(df_1h, "Min60") if df_1h is not None else "Error"
        self.monitoring_table.setItem(row, 2, QTableWidgetItem(state_1h))

        trend = "Alcista" if state_15m == "Alcista" and state_1h == "Alcista" else \
            "Bajista" if state_15m == "Bajista" and state_1h == "Bajista" else "Neutral"
        self.monitoring_table.setItem(row, 3, QTableWidgetItem(trend))

        if trend != self.previous_trends[coin]:
            self.previous_trends[coin] = trend
            self.alert_trend_change(coin, trend)

    def update_table(self):
        for row in range(len(self.coins)):
            self.update_row(row)
            self.monitoring_table.resizeColumnsToContents()

    def setup_timers(self):
        self.timers["Min15"] = QTimer()
        self.timers["Min15"].timeout.connect(lambda: self.update_timeframe_data("Min15"))
        self.timers["Min60"] = QTimer()
        self.timers["Min60"].timeout.connect(lambda: self.update_timeframe_data("Min60"))
        self.calculate_next_15m_update(self.timers["Min15"])
        self.calculate_next_hourly_update(self.timers["Min60"])

    def calculate_next_15m_update(self, timer):
        now = datetime.now(timezone.utc)
        minutes_until_next = 15 - now.minute % 15
        next_update = now + timedelta(minutes=minutes_until_next, seconds=-now.second + 5, microseconds=-now.microsecond)
        delay = (next_update - now).total_seconds() * 1000
        timer.start(int(delay))
        print(f"Próxima actualización (UTC): {format_utc_to_local(next_update)}")

    def calculate_next_hourly_update(self, timer):
        now = datetime.now(timezone.utc)
        next_update = now.replace(minute=0, second=5, microsecond=0) + timedelta(hours=1)
        delay = (next_update - now).total_seconds() * 1000
        timer.start(int(delay))
        print(f"Próxima actualización horaria (UTC): {format_utc_to_local(next_update)}")

    def update_timeframe_data(self, interval):
        print(f"{COLORS['azul']}🔄 Actualizando datos para {interval}{COLORS['reset']}")
        if interval == "Min60":
            self.update_hourly_data()
        self.update_table()
        if interval == "Min15":
            self.calculate_next_15m_update(self.timers[interval])
        else:
            self.calculate_next_hourly_update(self.timers[interval])

    def alert_trend_change(self, coin, new_trend):
        if new_trend == "Neutral":
            return

        current_time = datetime.now(timezone.utc)
        time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"{COLORS['amarillo']}🔔 ¡Cambio de tendencia! {coin}: {new_trend}{COLORS['reset']}")

        # Solo genera alerta si se cumple la lógica específica
        df_15m = self.fetch_historical_data(coin, "Min15")
        df_1h = self.hourly_data.get(coin)

        if df_15m is None or df_1h is None:
            return

        df_15m.ta.ema(length=21, append=True)
        df_1h.ta.ema(length=50, append=True)

        macd_15m = ta.macd(df_15m["close"])
        df_15m["macd"] = macd_15m["MACD_12_26_9"]
        df_15m["signal"] = macd_15m["MACDs_12_26_9"]

        macd_1h = ta.macd(df_1h["close"])
        df_1h["macd"] = macd_1h["MACD_12_26_9"]
        df_1h["signal"] = macd_1h["MACDs_12_26_9"]

        df_15m.dropna(inplace=True)
        df_1h.dropna(inplace=True)

        c15 = df_15m.iloc[-1]
        c1h = df_1h.iloc[-1]

        long_condition = c15["close"] > c15["EMA_21"] and c15["macd"] > c15["signal"] and \
                         c1h["close"] > c1h["EMA_50"] and c1h["macd"] > c1h["signal"]

        short_condition = c15["close"] < c15["EMA_21"] and c15["macd"] < c15["signal"] and \
                          c1h["close"] < c1h["EMA_50"] and c1h["macd"] < c1h["signal"]

        if not (long_condition or short_condition):
            return

        pygame.mixer.music.load("alert.wav") if os.path.exists("alert.wav") else None
        pygame.mixer.music.play()

        self.alert_log.insertRow(0)

        web_button = QPushButton()
        web_button.setIcon(qta.icon("mdi.web"))
        web_button.setStyleSheet("QPushButton { max-width: 20px; max-height: 20px; padding: 2px; margin: 0px; }")
        web_button.clicked.connect(lambda _, c=coin: self.open_web_page(c))
        self.alert_log.setCellWidget(0, 0, web_button)

        self.alert_log.setItem(0, 1, QTableWidgetItem(time_str))
        self.alert_log.setItem(0, 2, QTableWidgetItem(coin))
        self.alert_log.setItem(0, 3, QTableWidgetItem(f"Cambio a tendencia {new_trend}"))

        if self.alert_log.rowCount() > 50:
            self.alert_log.removeRow(50)

        self.alert_log.resizeColumnsToContents()

    def open_web_page(self, symbol):
        import webbrowser
        coin = symbol.replace('/USDT:USDT', '_USDT')
        url = f"https://futures.mexc.com/exchange/{coin}?type=linear_swap"
        webbrowser.open(url)

    def show_message(self, title, text):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Warning)
        msg.exec()

def main():
    app = QApplication(sys.argv)
    window = CryptoMonitorApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()


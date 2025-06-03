import ccxt
import sys
from datetime import datetime, timedelta, timezone
import time
import pandas as pd
import pandas_ta as ta
import pygame
import qtawesome as qta
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView, QLabel
)

COLORS = {
    "verde": "\033[92m",
    "rojo": "\033[91m",
    "reset": "\033[0m",
    "azul": "\033[94m",
    "amarillo": "\033[93m"
}


def format_utc_to_local(utc_dt):
    return utc_dt.strftime('%Y-%m-%d %H:%M:%S')


class CryptoMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Inicializar exchange MEXC con configuración
        self.exchange = ccxt.mexc()


        # Lista fija de monedas
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

        # Cargar datos horarios antes de iniciar
        print(f"{COLORS['azul']}🔄 Cargando datos horarios iniciales...{COLORS['reset']}")
        self.update_hourly_data()

        self.setup_timers()

        # Actualizar datos iniciales de 15 minutos
        QTimer.singleShot(1000, lambda: self.update_timeframe_data("Min15"))


    def setup_ui(self):
        self.setWindowTitle("Monitor  Futuros")
        self.setGeometry(100, 100, 1000, 800)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        self.monitoring_table = QTableWidget()
        self.setup_monitoring_table()
        self.initialize_table_data()
        layout.addWidget(self.monitoring_table)

        # Área de log de alertas
        self.alert_log = QTableWidget()
        self.setup_alert_log()
        layout.addWidget(self.alert_log)

        self.close_button = QPushButton("Cerrar Programa")
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)

    def setup_monitoring_table(self):
        headers = ["", "Moneda", "EMA200(15m)", "EMA50(1h)", "Tendencia"]  # Cambiado EMA20 a EMA200

        self.monitoring_table.setColumnCount(len(headers))
        self.monitoring_table.setHorizontalHeaderLabels(headers)

        self.monitoring_table.setColumnWidth(0, 22)
        self.monitoring_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        for col in range(2, len(headers)):
            self.monitoring_table.setColumnWidth(col, 100)
            self.monitoring_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Interactive)

    def setup_alert_log(self):
        self.alert_log.setColumnCount(3)
        self.alert_log.setHorizontalHeaderLabels(["Fecha/Hora (UTC)", "Moneda", "Cambio"])
        self.alert_log.setMaximumHeight(200)

        # Configurar el ancho de las columnas
        self.alert_log.setColumnWidth(0, 200)  # Fecha/Hora
        self.alert_log.setColumnWidth(1, 150)  # Moneda
        self.alert_log.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # Cambio

    def initialize_table_data(self):
        self.monitoring_table.setRowCount(len(self.coins))

        for row, coin in enumerate(self.coins):
            web_button = QPushButton()
            web_button.setIcon(qta.icon("mdi.web"))
            web_button.clicked.connect(lambda _, c=coin: self.open_web_page(c))
            web_button.setStyleSheet("""
                QPushButton {
                    max-width: 20px;
                    max-height: 20px;
                    padding: 2px;
                    margin: 0px;
                }
            """)
            self.monitoring_table.setCellWidget(row, 0, web_button)

            self.monitoring_table.setItem(row, 1, QTableWidgetItem(coin))

            for col in range(2, 5):
                self.monitoring_table.setItem(row, col, QTableWidgetItem("Cargando..."))

    def update_hourly_data(self):  # Cambiado de update_daily_data
        now = datetime.now(timezone.utc)
        if (self.last_hourly_update is None or
                (now - self.last_hourly_update).total_seconds() >= 3600):  # 1 hora en segundos
            print(f"{COLORS['azul']}🔄 Actualizando datos horarios{COLORS['reset']}")
            for coin in self.coins:
                df = self.fetch_historical_data(coin, "Min60")  # Cambiado de Day1 a Hour1
                if df is not None:
                    self.hourly_data[coin] = df
                    print(f"{COLORS['verde']}✅ Datos horarios actualizados para {coin}{COLORS['reset']}")
                else:
                    print(f"{COLORS['rojo']}❌ Error actualizando datos horarios para {coin}{COLORS['reset']}")
            self.last_hourly_update = now

    def fetch_historical_data(self, symbol, interval, retry_count=3):
        timeframe_map = {
            "Min15": "15m",
            "Min60": "1h"
        }

        timeframe = timeframe_map[interval]

        for attempt in range(retry_count):
            try:
                print(
                    f"{COLORS['azul']}🔄 Intentando descargar {symbol} ({interval}) - Intento {attempt + 1}{COLORS['reset']}")

                try:
                    ohlcv = self.exchange.fetch_ohlcv(
                        symbol,
                        timeframe,
                        limit=300
                    )
                except Exception as e:
                    if 'request timeout' in str(e).lower() or 'network' in str(e).lower():
                        self.reset_exchange()  # Cambiado de reconnect_exchange a reset_exchange
                        time.sleep(2)
                        continue
                    raise e

                if not ohlcv:
                    print(f"{COLORS['rojo']}❌ Sin datos para {symbol} ({interval}){COLORS['reset']}")
                    if attempt < retry_count - 1:
                        time.sleep(2)  # Aumentar el tiempo de espera entre intentos
                        continue
                    return None

                # Crear DataFrame
                df = pd.DataFrame(
                    ohlcv,
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )

                # Convertir timestamp de milisegundos a datetime
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)

                if df.empty:
                    print(f"{COLORS['rojo']}❌ No hay datos disponibles para {symbol} ({interval}){COLORS['reset']}")
                    return None

                df = df.sort_values("timestamp").reset_index(drop=True)

                last_candle_time = df["timestamp"].iloc[-2]
                local_time = format_utc_to_local(last_candle_time)
                print(f"{COLORS['verde']}✅ {symbol} ({interval}) procesado correctamente - "
                      f"Última vela cerrada (UTC): {local_time}{COLORS['reset']}")

                return df.iloc[:-1]

            except Exception as e:
                print(
                    f"{COLORS['rojo']}Error en {symbol} ({interval}): {str(e)} - Intento {attempt + 1}{COLORS['reset']}")
                if attempt < retry_count - 1:
                    time.sleep(2)
                    continue

        return None

    def calculate_indicators(self, df, timeframe):
        try:
            df = df.dropna(subset=["close"])
            if timeframe == "Min15":
                if len(df) < 210:
                    return "Error"
                ema = ta.ema(df["close"], length=200)
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

    def update_table(self):
        try:
            for row in range(len(self.coins)):
                self.update_row(row)
        except Exception as e:
            print(f"Error en update_table: {str(e)}")

    def update_row(self, row):
        try:
            coin = self.coins[row]

            web_button = QPushButton()
            web_button.setIcon(qta.icon("mdi.web"))
            web_button.clicked.connect(lambda _, c=coin: self.open_web_page(c))
            web_button.setStyleSheet("""
                QPushButton {
                    max-width: 20px;
                    max-height: 20px;
                    padding: 2px;
                    margin: 0px;
                }
            """)
            self.monitoring_table.setCellWidget(row, 0, web_button)

            self.monitoring_table.setItem(row, 1, QTableWidgetItem(coin))

            states = []

            # Actualizar datos de 15 minutos
            df_15m = self.fetch_historical_data(coin, "Min15")
            if df_15m is not None:
                state_15m = self.calculate_indicators(df_15m, "Min15")
                self.monitoring_table.setItem(row, 2, QTableWidgetItem(state_15m))
                states.append(state_15m)
            else:
                self.monitoring_table.setItem(row, 2, QTableWidgetItem("Error"))
                states.append("Error")

            # Usar datos horarios almacenados
            if self.hourly_data[coin] is not None:
                state_1h = self.calculate_indicators(self.hourly_data[coin], "Min60")  # Cambiado de Day1 a Hour1
                self.monitoring_table.setItem(row, 3, QTableWidgetItem(state_1h))
                states.append(state_1h)
            else:
                self.monitoring_table.setItem(row, 3, QTableWidgetItem("Error"))
                states.append("Error")

            if "Error" not in states:
                if all(state == "Alcista" for state in states):
                    trend = "Alcista"
                elif all(state == "Bajista" for state in states):
                    trend = "Bajista"
                else:
                    trend = "Neutral"

                if self.previous_trends[coin] is not None and trend != self.previous_trends[coin]:
                    if trend in ["Alcista", "Bajista"]:
                        self.alert_trend_change(coin, trend)

                self.previous_trends[coin] = trend
                self.monitoring_table.setItem(row, 4, QTableWidgetItem(trend))
            else:
                self.monitoring_table.setItem(row, 4, QTableWidgetItem("Error"))

        except Exception as e:
            print(f"Error actualizando fila {row}: {str(e)}")

    def setup_timers(self):
        timer_15m = QTimer(self)
        timer_15m.timeout.connect(lambda: self.update_timeframe_data("Min15"))
        self.calculate_next_15m_update(timer_15m)
        self.timers["Min15"] = timer_15m

        timer_60m = QTimer(self)
        timer_60m.timeout.connect(lambda: self.update_timeframe_data("Min60"))  # Cambiado a Min60
        self.calculate_next_hourly_update(timer_60m)
        self.timers["Min60"] = timer_60m  # Cambiado a Min60

    def calculate_next_15m_update(self, timer):
        now = datetime.now(timezone.utc)

        current_minute = now.minute
        minutes_until_next = 15 - (current_minute % 15)

        if minutes_until_next == 0:
            minutes_until_next = 15

        next_update = now + timedelta(
            minutes=minutes_until_next,
            seconds=-now.second + 5,
            microseconds=-now.microsecond
        )

        delay = (next_update - now).total_seconds() * 1000
        timer.start(int(delay))
        print(f"Próxima actualización (UTC): {format_utc_to_local(next_update)}")

    def calculate_next_hourly_update(self, timer):  # Nueva función para actualización horaria
        now = datetime.now(timezone.utc)
        next_update = now.replace(
            minute=0,
            second=5,
            microsecond=0
        ) + timedelta(hours=1)

        delay = (next_update - now).total_seconds() * 1000
        timer.start(int(delay))
        print(f"Próxima actualización horaria (UTC): {format_utc_to_local(next_update)}")

    def update_timeframe_data(self, interval):
        print(f"{COLORS['azul']}🔄 Actualizando datos para {interval}{COLORS['reset']}")

        if interval == "Min60":  # Cambiado Day1 a Hour1
            self.update_hourly_data()  # Cambiado de update_daily_data
            self.update_table()
        elif interval == "Min15":
            self.update_table()

        if interval == "Min15":
            self.calculate_next_15m_update(self.timers[interval])
        else:
            self.calculate_next_hourly_update(self.timers[interval])  # Cambiado a hour

    def alert_trend_change(self, coin, new_trend):
        current_time = datetime.now(timezone.utc)
        time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
        message = f"{coin}: {new_trend}"
        print(f"{COLORS['amarillo']}🔔 ¡Cambio de tendencia! {message}{COLORS['reset']}")

        try:
            pygame.mixer.music.load("alert.wav")
            pygame.mixer.music.play()
        except Exception as e:
            print(f"Error reproduciendo sonido: {str(e)}")

        # Insertar nueva alerta al principio del log
        self.alert_log.insertRow(0)
        self.alert_log.setItem(0, 0, QTableWidgetItem(time_str))
        self.alert_log.setItem(0, 1, QTableWidgetItem(coin))
        self.alert_log.setItem(0, 2, QTableWidgetItem(f"Cambio a tendencia {new_trend}"))

        # Mantener un máximo de filas (por ejemplo, 50)
        max_rows = 50
        if self.alert_log.rowCount() > max_rows:
            self.alert_log.removeRow(max_rows)

    def open_web_page(self, symbol):
        import webbrowser
        # Convertir de "ADA/USDT:USDT" a "ADA_USDT"
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
import json
import sys
import threading
from datetime import datetime, timedelta
import time
from datetime import datetime, timezone
from collections import defaultdict  # Añadir esta línea
import pandas as pd
import pandas_ta as ta
import pygame
import qtawesome as qta
import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QPushButton, QTableWidget, \
    QTableWidgetItem, QLineEdit, QComboBox, QMessageBox, QHeaderView, QLabel


COLORS = {
    "verde": "\033[92m",
    "rojo": "\033[91m",
    "reset": "\033[0m",
    "azul": "\033[94m",
    "amarillo": "\033[93m"
}
pygame.mixer.init()

def play_sound(sound_file):
    try:
        pygame.mixer.music.load(sound_file)
        pygame.mixer.music.play()
    except Exception as e:
        QMessageBox.warning(None, "Error de sonido", f"No se pudo reproducir el sonido: {str(e)}")


def format_utc_to_local(utc_dt, interval=None):
    if interval is None:
        local_dt = utc_dt.astimezone(timezone(timedelta(hours=-6)))
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')

    # Diccionario con los ajustes para cada intervalo
    interval_adjustments = {
        "Min5": timedelta(minutes=5),
        "Min15": timedelta(minutes=15),
        "Min30": timedelta(minutes=30),
        "Min60": timedelta(hours=1),
        "Hour4": timedelta(hours=4),
        "Day1": timedelta(days=1)
    }

    # Obtener el ajuste correspondiente al intervalo o usar 0 si no está definido
    adjustment = interval_adjustments.get(interval, timedelta(0))
    close_time = utc_dt + adjustment

    local_dt = close_time.astimezone(timezone(timedelta(hours=-6)))
    return local_dt.strftime('%Y-%m-%d %H:%M:%S')

class AlertButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.states = [None, "bullish", "bearish"]  # Estados: Off -> Alcista -> Bajista
        self.current_state = 0  # Comienza en Off (None)
        self.updateText()
        self.clicked.connect(self.cycleState)
        self.setStyleSheet("""
                    QPushButton {
                        border: none;
                        padding: 2px;
                        border-radius: 2px;
                        min-width: 60px;
                        max-width: 60px;
                        max-height: 20px;
                        margin: 0px;
                        text-align: left;
                    }
                """)

    def cycleState(self):
        self.current_state = (self.current_state + 1) % len(self.states)
        self.updateText()

    def updateText(self):
        state = self.states[self.current_state]
        if state is None:
            self.setText("⚪ Off")
            self.setStyleSheet("QPushButton { background-color: #444; color: white; }")
        elif state == "bullish":
            self.setText("🟢 Alcista")
            self.setStyleSheet("QPushButton { background-color: #1b5e20; color: white; }")
        else:  # bearish
            self.setText("🔴 Bajista")
            self.setStyleSheet("QPushButton { background-color: #b71c1c; color: white; }")

    def getState(self):
        return self.states[self.current_state]

class CryptoMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Crypto Monitor")
        self.setGeometry(100, 100, 1000, 600)

        self.timers = {}  # Temporizadores para cada temporalidad
        self.alert_states = {}  # Diccionario para almacenar el estado de las alertas
        self.alert_cooldown = False  # Estado de enfriamiento para las alertas
        self.alert_cooldown_timer = QTimer(self)  # Temporizador de enfriamiento
        self.alert_cooldown_timer.setSingleShot(True)
        self.alert_cooldown_timer.timeout.connect(self.reset_alert_cooldown)

        main_layout = QVBoxLayout()
        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        self.tab_widget = QTabWidget()

        # Tab de Monitoreo
        self.monitoring_tab = QWidget()
        self.monitoring_layout = QVBoxLayout()
        self.monitoring_table = QTableWidget()
        self.monitoring_table.setColumnCount(3)
        self.monitoring_table.setHorizontalHeaderLabels(["Moneda", "Tendencia", "Acción"])
        self.monitoring_layout.addWidget(self.monitoring_table)
        self.monitoring_tab.setLayout(self.monitoring_layout)
        self.coins = []  # Lista de monedas para monitoreo

        # Tab de Búsqueda
        self.search_tab = QWidget()
        self.search_layout = QVBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Introduce el nombre de la moneda...")
        self.search_layout.addWidget(self.search_input)

        self.search_button = QPushButton("Buscar")
        self.search_button.clicked.connect(self.add_coin_from_search)
        self.search_layout.addWidget(self.search_button)

        self.search_results_table = QTableWidget()
        self.search_results_table.setColumnCount(2)
        self.search_results_table.setHorizontalHeaderLabels(["Moneda", "Acción"])
        self.search_results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.search_layout.addWidget(self.search_results_table)

        self.search_tab.setLayout(self.search_layout)

        # Tab de Configuración
        self.settings_tab = QWidget()
        self.settings_layout = QVBoxLayout()
        self.indicators = []
        self.indicator_select = QComboBox()
        self.indicator_select.addItems(["Seleccionar Indicador", "EMA", "MACD"])
        self.indicator_select.currentIndexChanged.connect(self.update_parameter_fields)
        self.settings_layout.addWidget(self.indicator_select)
        self.ema_period_input = QLineEdit()
        self.ema_period_input.setPlaceholderText("Haz click para ingresar período")
        self.ema_period_input.setVisible(False)
        self.settings_layout.addWidget(self.ema_period_input)
        self.macd_fast_input = QLineEdit()
        self.macd_fast_input.setPlaceholderText("Periodo Rápido MACD")
        self.macd_fast_input.setVisible(False)
        self.macd_slow_input = QLineEdit()
        self.macd_slow_input.setPlaceholderText("Periodo Lento MACD")
        self.macd_slow_input.setVisible(False)
        self.macd_signal_input = QLineEdit()
        self.macd_signal_input.setPlaceholderText("Periodo Señal MACD")
        self.macd_signal_input.setVisible(False)
        self.settings_layout.addWidget(self.macd_fast_input)
        self.settings_layout.addWidget(self.macd_slow_input)
        self.settings_layout.addWidget(self.macd_signal_input)
        self.timeframe_select = QComboBox()
        self.timeframe_select.addItems(["Seleccionar Temporalidad", "5m", "15m", "1h", "4h", "1d"])
        self.timeframe_select.setVisible(False)
        self.settings_layout.addWidget(self.timeframe_select)
        self.save_indicator_button = QPushButton("Guardar Indicador")
        self.save_indicator_button.clicked.connect(self.save_indicator)
        self.settings_layout.addWidget(self.save_indicator_button)
        self.indicator_table = QTableWidget()
        self.indicator_table.setColumnCount(5)
        self.indicator_table.setHorizontalHeaderLabels(
            ["Indicador", "Parámetros", "Temporalidad", "Editar", "Eliminar"]
        )
        self.settings_layout.addWidget(self.indicator_table)
        self.settings_tab.setLayout(self.settings_layout)

        # Tabs
        self.tab_widget.addTab(self.monitoring_tab, "Monitoreo")
        self.tab_widget.addTab(self.search_tab, "Búsqueda")
        self.tab_widget.addTab(self.settings_tab, "Configuración")

        # Botones principales
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.handle_cancel)
        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(self.cancel_button)
        self.close_button = QPushButton("Cerrar Programa")
        self.close_button.clicked.connect(self.close_program)
        main_layout.addWidget(self.close_button)

        # Cargar monedas guardadas y configuraciones
        self.load_coins_from_file()  # Cargar monedas al iniciar
        self.load_indicators_from_file()  # Cargar indicadores al iniciar

        self.alert_states = defaultdict(lambda: {"last_trend": None})

    def add_coin_to_monitoring(self, coin):
        if not any(c["name"] == coin for c in self.coins):  # Evitar duplicados
            self.coins.append({"name": coin})
            self.save_coins_to_file()  # Guardar las monedas en el archivo
            self.update_table()  # Actualizar la tabla de monitoreo
        else:
            self.show_message("Advertencia", f"La moneda {coin} ya está en la lista de monitoreo.")

    def remove_coin(self, row):
        confirm = QMessageBox.question(
            self,
            "Confirmación",
            "¿Deseás eliminar esta moneda del monitoreo?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.coins.pop(row)
            self.save_coins_to_file()
            self.update_table()

    def save_coins_to_file(self):
        try:
            with open("coins.json", "w") as file:
                json.dump(self.coins, file)
        except Exception as e:
            self.show_message("Error", f"No se pudo guardar las monedas: {e}")

    def reset_alert_cooldown(self):
        self.alert_cooldown = False

    def update_table(self):
        try:
            self.monitoring_table.clear()  # Limpia la tabla antes de configurarla

            # Caso 1: No hay monedas ni indicadores
            if not self.coins and not self.indicators:
                self.monitoring_table.setRowCount(1)
                self.monitoring_table.setColumnCount(1)
                self.monitoring_table.setHorizontalHeaderLabels(["Mensaje"])
                add_coin_button = QPushButton("Agregar moneda")
                add_coin_button.clicked.connect(
                    lambda: self.tab_widget.setCurrentIndex(1))  # Ir a la pestaña de búsqueda
                widget = QWidget()
                layout = QVBoxLayout(widget)
                layout.addWidget(QLabel("Por favor, agrega una moneda."))
                layout.addWidget(add_coin_button)
                self.monitoring_table.setCellWidget(0, 0, widget)
                return

            if self.coins and not self.indicators:
                self.monitoring_table.setRowCount(len(self.coins))
                # Cambiar de 4 a 3 columnas
                self.monitoring_table.setColumnCount(3)
                # Quitar "Agregar Indicador" de las etiquetas
                self.monitoring_table.setHorizontalHeaderLabels(["", "", "Moneda"])

                for row, coin in enumerate(self.coins):
                    # Botón de eliminar (más pequeño)
                    delete_button = QPushButton()
                    delete_button.setIcon(qta.icon("mdi.delete"))
                    delete_button.clicked.connect(lambda _, r=row: self.remove_coin(r))
                    delete_button.setStyleSheet("""
                        QPushButton {
                            max-width: 20px;
                            max-height: 20px;
                            padding: 2px;
                            margin: 0px;
                        }
                    """)
                    self.monitoring_table.setCellWidget(row, 0, delete_button)

                    # Botón para abrir web (más pequeño)
                    web_button = QPushButton()
                    web_button.setIcon(qta.icon("mdi.web"))
                    web_button.clicked.connect(lambda _, c=coin["name"]: self.open_web_page(c))
                    web_button.setStyleSheet("""
                        QPushButton {
                            max-width: 20px;
                            max-height: 20px;
                            padding: 2px;
                            margin: 0px;
                        }
                    """)
                    self.monitoring_table.setCellWidget(row, 1, web_button)

                    # Nombre de la moneda
                    self.monitoring_table.setItem(row, 2, QTableWidgetItem(coin["name"]))
                return

            # Caso 3: Hay indicadores, pero no hay monedas
            if not self.coins and self.indicators:
                self.monitoring_table.setRowCount(1)
                self.monitoring_table.setColumnCount(1)
                self.monitoring_table.setHorizontalHeaderLabels(["Mensaje"])
                add_coin_button = QPushButton("Agregar moneda")
                add_coin_button.clicked.connect(
                    lambda: self.tab_widget.setCurrentIndex(1))  # Ir a la pestaña de búsqueda
                widget = QWidget()
                layout = QVBoxLayout(widget)
                layout.addWidget(QLabel("Por favor, agrega una moneda."))
                layout.addWidget(add_coin_button)
                self.monitoring_table.setCellWidget(0, 0, widget)
                return

            # Caso 4: Hay monedas e indicadores
            num_columns = 5 + len(self.indicators)  # Moneda, Eliminar, Web, Alerta, Indicadores, Tendencia
            self.monitoring_table.setRowCount(len(self.coins))
            self.monitoring_table.setColumnCount(num_columns)

            # Configuración de cabeceras (nuevo orden)
            header_labels = ["", "", "Alerta", "Moneda"] + [f"{ind['name']} ({ind['timeframe']})" for ind in
                                                            self.indicators] + [
                                "Tendencia"]
            self.monitoring_table.setHorizontalHeaderLabels(header_labels)

            self.monitoring_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            self.monitoring_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
            self.monitoring_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
            self.monitoring_table.setColumnWidth(0, 22)  # Columna del botón eliminar
            self.monitoring_table.setColumnWidth(1, 22)  # Columna del botón web
            self.monitoring_table.setColumnWidth(2, 65)  # Columna del botón alerta

            for row, coin in enumerate(self.coins):
                try:
                    # Botón de eliminar (más pequeño)
                    delete_button = QPushButton()
                    delete_button.setIcon(qta.icon("mdi.delete"))
                    delete_button.clicked.connect(lambda _, r=row: self.remove_coin(r))
                    delete_button.setStyleSheet("""
                        QPushButton {
                            max-width: 20px;
                            max-height: 20px;
                            padding: 2px;
                            margin: 0px;
                        }
                    """)
                    self.monitoring_table.setCellWidget(row, 0, delete_button)

                    # Botón para abrir web (más pequeño)
                    web_button = QPushButton()
                    web_button.setIcon(qta.icon("mdi.web"))
                    web_button.clicked.connect(lambda _, c=coin["name"]: self.open_web_page(c))
                    web_button.setStyleSheet("""
                        QPushButton {
                            max-width: 20px;
                            max-height: 20px;
                            padding: 2px;
                            margin: 0px;
                        }
                    """)
                    self.monitoring_table.setCellWidget(row, 1, web_button)

                    # Botón de alerta (nuevo orden)
                    alert_button = AlertButton()
                    alert_button.clicked.connect(lambda _, c=coin["name"]: self.on_alert_change(c, alert_button))
                    self.monitoring_table.setCellWidget(row, 2, alert_button)

                    # Nombre de la moneda
                    self.monitoring_table.setItem(row, 3, QTableWidgetItem(coin["name"]))

                    # Cálculo de indicadores
                    indicator_states = []
                    for col, indicator in enumerate(self.indicators, start=4):
                        try:
                            interval = self.map_interval(indicator.get("timeframe"))
                            if not interval:
                                self.monitoring_table.setItem(row, col, QTableWidgetItem("Intervalo Inválido"))
                                indicator_states.append("Error")
                                continue

                            coin_data = self.fetch_historical_data(coin["name"], interval)
                            if coin_data is None or coin_data.empty:
                                self.monitoring_table.setItem(row, col, QTableWidgetItem("Error"))
                                indicator_states.append("Error")
                                continue

                            if indicator.get("name") == "EMA":
                                params = indicator.get("parameters", "").split(": ")
                                if len(params) > 1:
                                    period = int(params[1])
                                    ema = ta.ema(coin_data["close"], length=period)
                                    state = "Alcista" if coin_data["close"].iloc[-2] > ema.iloc[-2] else "Bajista"
                                else:
                                    state = "Error"
                            elif indicator.get("name") == "MACD":
                                try:
                                    params = [x.split(": ")[1] for x in indicator.get("parameters", "").split(", ")]
                                    fast, slow, signal = map(int, params)
                                    macd = ta.macd(coin_data["close"], fast=fast, slow=slow, signal=signal)
                                    state = "Alcista" if macd["MACD_12_26_9"].iloc[-2] > macd["MACDs_12_26_9"].iloc[
                                        -2] else "Bajista"
                                except:
                                    state = "Error"
                            else:
                                state = "Error"

                            self.monitoring_table.setItem(row, col, QTableWidgetItem(state))
                            indicator_states.append(state)
                        except Exception as e:
                            print(f"Error procesando indicador: {str(e)}")
                            self.monitoring_table.setItem(row, col, QTableWidgetItem("Error"))
                            indicator_states.append("Error")

                    # Determinar tendencia general
                    if all(state == "Alcista" for state in indicator_states):
                        trend = "Alcista"
                    elif all(state == "Bajista" for state in indicator_states):
                        trend = "Bajista"
                    else:
                        trend = "Neutral"

                    # Mostrar tendencia
                    self.monitoring_table.setItem(row, num_columns - 1, QTableWidgetItem(trend))

                    # Procesar alertas
                    self.process_alert(coin["name"], trend, alert_button)

                except Exception as e:
                    print(f"Error en el procesamiento de la fila {row}: {str(e)}")

        except Exception as e:
            print(f"Error general en update_table: {str(e)}")

    def process_alert(self, coin_name, trend, alert_button):
        try:
            if coin_name not in self.alert_states:
                self.alert_states[coin_name] = {"last_trend": None}

            last_trend = self.alert_states[coin_name].get("last_trend")
            current_alert_state = alert_button.getState()

            if (trend != last_trend and
                    ((current_alert_state == "bullish" and trend == "Alcista") or
                     (current_alert_state == "bearish" and trend == "Bajista")) and
                    not self.alert_cooldown):
                alert_message = f"La tendencia para {coin_name} es {trend}."
                sound_file = "alert.wav"
                threading.Thread(target=play_sound, args=(sound_file,)).start()
                QMessageBox.information(self, "Alerta de Tendencia", alert_message)
                self.alert_cooldown = True
                self.alert_cooldown_timer.start(60000)

            self.alert_states[coin_name]["last_trend"] = trend

        except Exception as e:
            print(f"Error al procesar alerta para {coin_name}: {str(e)}")
            self.alert_states[coin_name] = {"last_trend": None}

    def on_alert_change(self, coin, button):
        self.alert_states[coin] = button.getState()
        state_text = {None: "desactivada", "bullish": "alcista", "bearish": "bajista"}
        print(f"Alerta para {coin} cambiada a: {state_text[button.getState()]}")

    def fetch_historical_data(self, coin, interval, retry_count=3):

        url = f"https://contract.mexc.com/api/v1/contract/kline/{coin}?interval={interval}&limit=100"

        for attempt in range(retry_count):
            try:
                print(
                    f"{COLORS['azul']}🔄 Intentando descargar {coin} ({interval}) - Intento {attempt + 1}{COLORS['reset']}")

                response = requests.get(url, timeout=30)
                if response.status_code != 200:
                    print(f"{COLORS['rojo']}❌ Error {response.status_code} para {coin} ({interval}){COLORS['reset']}")
                    if attempt < retry_count - 1:
                        time.sleep(1)
                        continue
                    return None

                data = response.json()
                if not data.get("success") or "data" not in data:
                    print(f"{COLORS['rojo']}❌ Sin datos para {coin} ({interval}){COLORS['reset']}")
                    if attempt < retry_count - 1:
                        time.sleep(1)
                        continue
                    return None

                # Convertir los datos a DataFrame
                df = pd.DataFrame({
                    "timestamp": pd.to_datetime([t for t in data["data"]["time"]], unit='s', utc=True),
                    "open": pd.to_numeric(data["data"]["open"], errors='coerce'),
                    "high": pd.to_numeric(data["data"]["high"], errors='coerce'),
                    "low": pd.to_numeric(data["data"]["low"], errors='coerce'),
                    "close": pd.to_numeric(data["data"]["close"], errors='coerce'),
                    "volume": pd.to_numeric(data["data"]["vol"], errors='coerce')
                })

                if df.empty:
                    print(f"{COLORS['rojo']}❌ No hay datos disponibles para {coin} ({interval}){COLORS['reset']}")
                    return None

                # Calcular el inicio de la vela actual
                now = datetime.now(timezone.utc)
                interval_minutes = {
                    "Min5": 5,
                    "Min15": 15,
                    "Min60": 60,
                    "Hour4": 240,
                    "Day1": 1440
                }.get(interval)

                if interval_minutes is None:
                    print(f"{COLORS['rojo']}❌ Intervalo inválido: {interval}{COLORS['reset']}")
                    return None

                current_candle_start = now.replace(
                    minute=now.minute - (now.minute % interval_minutes),
                    second=0,
                    microsecond=0
                )

                # Verificar si la última vela en los datos está cerrada
                latest_timestamp = df["timestamp"].iloc[-1]

                if latest_timestamp >= current_candle_start:
                    print(f"{COLORS['amarillo']}⚠️ Detectada vela incompleta en {coin} ({interval}){COLORS['reset']}")
                    df = df.iloc[:-1]

                    if df.empty:
                        print(f"{COLORS['rojo']}❌ No hay suficientes datos para {coin} ({interval}){COLORS['reset']}")
                        return None

                last_candle_time = df["timestamp"].iloc[-1]
                local_close_time = format_utc_to_local(last_candle_time, interval)
                print(f"{COLORS['verde']}✅ {coin} ({interval}) procesado correctamente - "
                      f"Última vela cerrada: {local_close_time}{COLORS['reset']}")

                return df

            except Exception as e:
                print(
                    f"{COLORS['rojo']}Error en {coin} ({interval}): {str(e)} - Intento {attempt + 1}{COLORS['reset']}")
                if attempt < retry_count - 1:
                    time.sleep(1)
                    continue

        return None

    def fetch_all_data(self, symbols, timeframes):
        if not symbols or not timeframes:
            self.show_message("Error", "Por favor, agrega monedas e indicadores antes de descargar datos.")
            return {}
        print(f"\n{COLORS['azul']}🚀 Iniciando descarga de datos para {len(symbols)} símbolos{COLORS['reset']}")
        start_time = datetime.now()

        results = {}
        for symbol in symbols:
            results[symbol] = {}
            for timeframe in timeframes:
                interval = self.map_interval(timeframe)
                if interval:
                    data = self.fetch_historical_data(symbol, interval)
                    results[symbol][timeframe] = data
                    if data is not None:
                        print(f"{COLORS['verde']}✅ {symbol} ({timeframe}) procesado correctamente{COLORS['reset']}")
                    else:
                        print(f"{COLORS['rojo']}❌ Error procesando {symbol} ({timeframe}){COLORS['reset']}")

        duration = (datetime.now() - start_time).total_seconds()
        print(f"\n{COLORS['verde']}✨ Descarga completada en {duration:.2f} segundos{COLORS['reset']}")
        print(f"{COLORS['verde']}📊 Total de requests: {len(symbols) * len(timeframes)}{COLORS['reset']}\n")

        return results

    def save_indicator(self):
        if hasattr(self, "editing_row") and self.editing_row is not None:
            row = self.editing_row
        else:
            if len(self.indicators) >= 6:
                self.show_message("Error", "No se pueden agregar más de 6 indicadores.")
                return
            row = len(self.indicators)

        selected_indicator = self.indicator_select.currentText()
        timeframe = self.timeframe_select.currentText()

        if selected_indicator == "Seleccionar Indicador":
            self.show_message("Error", "Por favor, selecciona un indicador.")
            return

        if timeframe == "Seleccionar Temporalidad":
            self.show_message("Error", "Por favor, selecciona una temporalidad.")
            return

        if selected_indicator == "EMA":
            period = self.ema_period_input.text()
            if not period.isdigit():
                self.show_message("Error", "Por favor, ingresa un período válido.")
                return
            period = int(period)
            if period > 500:
                self.show_message("Error", "El período no puede ser mayor a 500.")
                return
            indicator_data = {"name": "EMA", "parameters": f"Período: {period}", "timeframe": timeframe}
        elif selected_indicator == "MACD":
            fast = self.macd_fast_input.text()
            slow = self.macd_slow_input.text()
            signal = self.macd_signal_input.text()
            if not (fast.isdigit() and slow.isdigit() and signal.isdigit()):
                self.show_message("Error", "Por favor, ingresa todos los parámetros del MACD.")
                return
            fast, slow, signal = int(fast), int(slow), int(signal)
            if fast > 500 or slow > 500 or signal > 500:
                self.show_message("Error", "Los períodos del MACD no pueden ser mayores a 500.")
                return
            indicator_data = {
                "name": "MACD",
                "parameters": f"Rápido: {fast}, Lento: {slow}, Señal: {signal}",
                "timeframe": timeframe,
            }
        else:
            self.show_message("Error", "Indicador no válido.")
            return

        if row < len(self.indicators):
            self.indicators[row] = indicator_data
        else:
            self.indicators.append(indicator_data)

        # Configurar el temporizador para la temporalidad del indicador
        if timeframe not in self.timers:
            self.setup_timer_for_timeframe(timeframe)

        self.update_indicator_table()  # Actualizar tabla de configuración
        self.save_indicators_to_file()  # Guardar indicadores
        self.update_table()  # Forzar actualización de la tabla de monitoreo
        self.reset_fields()
        self.editing_row = None

    def save_indicators_to_file(self):
        try:
            with open("indicators.json", "w") as file:
                json.dump(self.indicators, file)
        except Exception as e:
            self.show_message("Error", f"No se pudo guardar los indicadores: {e}")

    def load_indicators_from_file(self):
        try:
            with open("indicators.json", "r") as file:
                self.indicators = json.load(file)
                self.update_indicator_table()  # Actualiza la tabla de indicadores
                self.update_table()  # Actualiza la tabla de monitoreo

                # Configurar temporizadores para cada temporalidad
                for indicator in self.indicators:
                    self.setup_timer_for_timeframe(indicator["timeframe"])
        except FileNotFoundError:
            self.indicators = []  # Si no existe el archivo, inicia con una lista vacía
        except Exception as e:
            self.show_message("Error", f"No se pudo cargar los indicadores: {e}")

    def load_coins_from_file(self):
        try:
            with open("coins.json", "r") as file:
                self.coins = json.load(file)
                self.update_table()  # Actualiza la tabla al cargar las monedas
        except FileNotFoundError:
            self.coins = []  # Si el archivo no existe, iniciamos con una lista vacía
        except Exception as e:
            self.show_message("Error", f"No se pudo cargar las monedas: {e}")

    def fetch_coins_from_mexc(self):
        url = "https://contract.mexc.com/api/v1/contract/detail"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    coins = [item["symbol"] for item in data["data"]]
                    return coins
                else:
                    self.show_message("Error", "Error en la respuesta de MEXC.")
                    return []
            else:
                self.show_message("Error", f"Error al conectar con MEXC: {response.status_code}")
                return []
        except Exception as e:
            self.show_message("Error", f"Error al obtener monedas de MEXC: {e}")
            return []

    def add_coin_from_search(self):
        query = self.search_input.text().strip().upper()
        if not query:
            self.show_message("Error", "Por favor, introduce el nombre de una moneda.")
            return

        coins = self.fetch_coins_from_mexc()
        if not coins:
            self.show_message("Error", "No se encontraron monedas.")
            return

        filtered_coins = [coin for coin in coins if query in coin]

        if not filtered_coins:
            self.show_message("Error", f"No se encontraron monedas para '{query}'.")
            return

        self.search_results_table.setRowCount(len(filtered_coins))
        for row, coin in enumerate(filtered_coins):
            self.search_results_table.setItem(row, 0, QTableWidgetItem(coin))
            add_button = QPushButton("Agregar")
            add_button.clicked.connect(lambda _, c=coin: self.add_coin_to_monitoring(c))
            self.search_results_table.setCellWidget(row, 1, add_button)

    def update_indicator_table(self):
        self.indicator_table.setRowCount(len(self.indicators))
        self.indicator_table.setColumnCount(7)

        for row, indicator in enumerate(self.indicators):
            self.indicator_table.setItem(row, 0, QTableWidgetItem(indicator["name"]))
            self.indicator_table.setItem(row, 1, QTableWidgetItem(indicator["parameters"]))
            self.indicator_table.setItem(row, 2, QTableWidgetItem(indicator["timeframe"]))

            edit_button = QPushButton("Editar")
            edit_button.clicked.connect(lambda _, r=row: self.edit_indicator(r))
            self.indicator_table.setCellWidget(row, 3, edit_button)

            delete_button = QPushButton("Eliminar")
            delete_button.clicked.connect(lambda _, r=row: self.remove_indicator(r))
            self.indicator_table.setCellWidget(row, 4, delete_button)

            move_up_button = QPushButton("↑")
            move_up_button.clicked.connect(lambda _, r=row: self.move_indicator_up(r))
            self.indicator_table.setCellWidget(row, 5, move_up_button)

            move_down_button = QPushButton("↓")
            move_down_button.clicked.connect(lambda _, r=row: self.move_indicator_down(r))
            self.indicator_table.setCellWidget(row, 6, move_down_button)

        self.indicator_table.setHorizontalHeaderLabels(
            ["Indicador", "Parámetros", "Temporalidad", "Editar", "Eliminar", "↑", "↓"]
        )
        self.indicator_table.resizeColumnsToContents()

    def edit_indicator(self, row):
        self.editing_row = row
        selected_indicator = self.indicators[row]
        self.indicator_select.setCurrentText(selected_indicator["name"])

        if "EMA" in selected_indicator["name"]:
            self.ema_period_input.setVisible(True)
            self.macd_fast_input.setVisible(False)
            self.macd_slow_input.setVisible(False)
            self.macd_signal_input.setVisible(False)
            self.ema_period_input.setText(selected_indicator["parameters"].split(": ")[1])
        elif "MACD" in selected_indicator["name"]:
            self.ema_period_input.setVisible(False)
            self.macd_fast_input.setVisible(True)
            self.macd_slow_input.setVisible(True)
            self.macd_signal_input.setVisible(True)
            params = selected_indicator["parameters"].split(", ")
            self.macd_fast_input.setText(params[0].split(": ")[1])
            self.macd_slow_input.setText(params[1].split(": ")[1])
            self.macd_signal_input.setText(params[2].split(": ")[1])

        self.timeframe_select.setCurrentText(selected_indicator["timeframe"])
        self.cancel_button.setVisible(True)

    def remove_indicator(self, row):
        confirm = QMessageBox.question(
            self,
            "Confirmación",
            "¿Estás seguro de que deseas eliminar este indicador?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                if 0 <= row < len(self.indicators):
                    self.indicators.pop(row)
                    self.save_indicators_to_file()
                    self.update_indicator_table()
                    self.update_table()
            except Exception as e:
                self.show_message("Error", f"Error al eliminar el indicador: {str(e)}")

    def move_indicator_up(self, row):
        if row > 0:
            self.indicators[row], self.indicators[row - 1] = self.indicators[row - 1], self.indicators[row]
            self.update_indicator_table()
            self.save_indicators_to_file()
            self.update_table()

    def move_indicator_down(self, row):
        if row < len(self.indicators) - 1:
            self.indicators[row], self.indicators[row + 1] = self.indicators[row + 1], self.indicators[row]
            self.update_indicator_table()
            self.save_indicators_to_file()
            self.update_table()

    def reset_fields(self):
        self.indicator_select.setCurrentIndex(0)
        self.ema_period_input.clear()
        self.macd_fast_input.clear()
        self.macd_slow_input.clear()
        self.macd_signal_input.clear()
        self.timeframe_select.setCurrentIndex(0)
        self.search_input.clear()
        self.search_results_table.setRowCount(0)
        self.update_parameter_fields()

    def cancel_edit(self):
        self.reset_fields()
        self.editing_row = None

    def handle_cancel(self):
        current_tab = self.tab_widget.currentIndex()
        if current_tab == 1:
            self.reset_fields()
        elif current_tab == 2:
            self.cancel_edit()

    def update_parameter_fields(self):
        selected_indicator = self.indicator_select.currentText()

        if selected_indicator == "EMA":
            self.ema_period_input.setVisible(True)
            self.macd_fast_input.setVisible(False)
            self.macd_slow_input.setVisible(False)
            self.macd_signal_input.setVisible(False)
            self.timeframe_select.setVisible(True)
        elif selected_indicator == "MACD":
            self.ema_period_input.setVisible(False)
            self.macd_fast_input.setVisible(True)
            self.macd_slow_input.setVisible(True)
            self.macd_signal_input.setVisible(True)
            self.timeframe_select.setVisible(True)

            self.macd_fast_input.setText("12")
            self.macd_slow_input.setText("26")
            self.macd_signal_input.setText("9")
        else:
            self.ema_period_input.setVisible(False)
            self.macd_fast_input.setVisible(False)
            self.macd_slow_input.setVisible(False)
            self.macd_signal_input.setVisible(False)
            self.timeframe_select.setVisible(False)

    def map_interval(self, interval):
        mapping = {
            "5m": "Min5",
            "15m": "Min15",
            "1h": "Min60",
            "4h": "Hour4",
            "1d": "Day1"
        }
        return mapping.get(interval)

    def get_time_to_next_candle(self, timeframe):
        now = datetime.now(timezone.utc)  # Usar UTC
        processing_delay = 5  # Segundos de delay para dar tiempo al exchange

        if timeframe == "15m":
            minutes_until_next = 15 - (now.minute % 15)
            if minutes_until_next == 0:
                minutes_until_next = 15
            next_candle = now + timedelta(
                minutes=minutes_until_next,
                seconds=-now.second + processing_delay,
                microseconds=-now.microsecond
            )
        elif timeframe == "1h":
            next_candle = now + timedelta(
                hours=1,
                minutes=-now.minute,
                seconds=-now.second + processing_delay,
                microseconds=-now.microsecond
            )
        else:
            return None

        wait_time = (next_candle - now).total_seconds()
        next_candle_local = format_utc_to_local(next_candle)
        print(f"Próxima actualización de {timeframe} programada para: {next_candle_local}")
        return wait_time * 1000  # Convertir a milisegundos

    def setup_timer_for_timeframe(self, timeframe):
        if timeframe in self.timers:
            self.timers[timeframe].stop()

        time_to_next_candle = self.get_time_to_next_candle(timeframe)
        if time_to_next_candle is not None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self.update_timeframe_data(timeframe))
            timer.start(time_to_next_candle)
            self.timers[timeframe] = timer

            next_update = datetime.now(timezone.utc) + timedelta(milliseconds=time_to_next_candle)
            print(f"{COLORS['azul']}⏰ Próxima actualización de {timeframe}: "
                  f"{format_utc_to_local(next_update)}{COLORS['reset']}")

    def get_active_timeframes(self):
        active_timeframes = set()
        for indicator in self.indicators:
            active_timeframes.add(indicator['timeframe'])
        return sorted(list(active_timeframes))

    def should_update_timeframe(self, timeframe):
        now = datetime.now(timezone.utc)

        if timeframe == "15m":
            return now.minute % 15 == 0
        elif timeframe == "1h":
            return now.minute == 0
        elif timeframe == "4h":
            return now.hour % 4 == 0 and now.minute == 0
        elif timeframe == "1d":
            return now.hour == 0 and now.minute == 0

        return False

    def setup_timers(self):
        """
        Configura los temporizadores solo para las temporalidades activas
        """
        # Detener todos los timers existentes
        for timer in self.timers.values():
            timer.stop()
        self.timers.clear()

        # Obtener temporalidades activas
        active_timeframes = self.get_active_timeframes()

        for timeframe in active_timeframes:
            time_to_next = self.get_time_to_next_candle(timeframe)
            if time_to_next is not None:
                print(f"{COLORS['azul']}⏰ Próxima actualización de {timeframe}: "
                      f"en {time_to_next / 1000:.0f} segundos{COLORS['reset']}")

                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda tf=timeframe: self.update_timeframe_data(tf))
                timer.start(time_to_next)
                self.timers[timeframe] = timer

    def update_timeframe_data(self, timeframe):
        if not self.should_update_timeframe(timeframe):
            print(f"{COLORS['amarillo']}⚠️ Omitiendo actualización innecesaria de {timeframe}{COLORS['reset']}")
            return

        print(f"{COLORS['azul']}🔄 Actualizando datos para {timeframe}{COLORS['reset']}")

        interval = self.map_interval(timeframe)
        if not interval:
            print(f"{COLORS['rojo']}❌ Intervalo inválido: {timeframe}{COLORS['reset']}")
            return

        for coin in self.coins:
            df = self.fetch_historical_data(coin["name"], interval)
            if df is not None:
                print(f"{COLORS['verde']}✅ Datos actualizados para {coin['name']} ({timeframe}){COLORS['reset']}")
            else:
                print(f"{COLORS['rojo']}❌ Error actualizando datos para {coin['name']} ({timeframe}){COLORS['reset']}")

        # Actualizar la tabla
        self.update_table()

        # Configurar el próximo timer para este timeframe
        self.setup_timer_for_timeframe(timeframe)


    def handle_candle_close(self, timeframe):
        relevant_indicators = [ind for ind in self.indicators if ind["timeframe"] == timeframe]
        if relevant_indicators:
            self.update_table()

        # Programar el siguiente cierre de vela
        self.setup_timer_for_timeframe(timeframe)

    def show_message(self, title, text):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setIcon(QMessageBox.Warning)
        msg.exec()

    def open_web_page(self, coin):
        import webbrowser
        url = f"https://futures.mexc.com/exchange/{coin}?type=linear_swap"
        webbrowser.open(url)

    def close_program(self):
        self.close()


def main():
    app = QApplication(sys.argv)
    window = CryptoMonitorApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
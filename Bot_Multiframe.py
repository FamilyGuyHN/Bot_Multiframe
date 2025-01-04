import pygame
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta
import sys
import requests
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QPushButton, QTableWidget, \
    QTableWidgetItem, QLineEdit, QComboBox, QMessageBox, QHeaderView, QStyle, QLabel
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
import json
import qtawesome as qta

pygame.mixer.init()

def play_sound(sound_file):
    try:
        pygame.mixer.music.load(sound_file)
        pygame.mixer.music.play()
    except Exception as e:
        QMessageBox.warning(None, "Error de sonido", f"No se pudo reproducir el sonido: {str(e)}")


class CryptoMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Crypto Monitor")
        self.setGeometry(100, 100, 800, 600)

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

    def get_indicator_parameters(self, indicator):
        if "EMA" in indicator["name"]:
            period = indicator["parameters"].split(": ")[1]
            return f"{period} periodos"
        elif "MACD" in indicator["name"]:
            params = indicator["parameters"].split(", ")
            fast = params[0].split(": ")[1]
            slow = params[1].split(": ")[1]
            signal = params[2].split(": ")[1]
            return f"{fast}, {slow}, {signal}"
        return ""

    def update_table(self):
        try:
            self.monitoring_table.clear()  # Limpia la tabla antes de configurarla

            # Caso 1: No hay monedas ni indicadores
            if not self.coins and not self.indicators:
                self.monitoring_table.setRowCount(1)
                self.monitoring_table.setColumnCount(1)
                self.monitoring_table.setHorizontalHeaderLabels(["Mensaje"])
                msg_item = QTableWidgetItem("Por favor, agrega una moneda.")
                self.monitoring_table.setItem(0, 0, msg_item)

                # Botón para llevar a la sección de búsqueda
                add_coin_button = QPushButton("Agregar moneda")
                add_coin_button.clicked.connect(
                    lambda: self.tab_widget.setCurrentIndex(1))  # Ir a la pestaña de búsqueda
                self.monitoring_table.setCellWidget(0, 0, add_coin_button)
                return

            # Caso 2: Hay monedas, pero no indicadores
            if self.coins and not self.indicators:
                self.monitoring_table.setRowCount(len(self.coins))
                self.monitoring_table.setColumnCount(4)
                self.monitoring_table.setHorizontalHeaderLabels(["", "", "Moneda", "Agregar Indicador"])

                for row, coin in enumerate(self.coins):
                    # Botón de eliminar
                    delete_button = QPushButton()
                    delete_button.setIcon(qta.icon("mdi.delete"))
                    delete_button.clicked.connect(lambda _, r=row: self.remove_coin(r))
                    self.monitoring_table.setCellWidget(row, 0, delete_button)

                    # Botón para abrir web
                    web_button = QPushButton()
                    web_button.setIcon(qta.icon("mdi.web"))
                    web_button.clicked.connect(lambda _, c=coin["name"]: self.open_web_page(c))
                    self.monitoring_table.setCellWidget(row, 1, web_button)

                    # Nombre de la moneda
                    self.monitoring_table.setItem(row, 2, QTableWidgetItem(coin["name"]))

                    # Botón para agregar indicador
                    add_indicator_button = QPushButton("Agregar indicador")
                    add_indicator_button.clicked.connect(
                        lambda: self.tab_widget.setCurrentIndex(2))  # Ir a configuración
                    self.monitoring_table.setCellWidget(row, 3, add_indicator_button)
                return

            # Caso 3: Hay indicadores, pero no hay monedas
            if not self.coins and self.indicators:
                self.monitoring_table.setRowCount(1)
                self.monitoring_table.setColumnCount(1)
                self.monitoring_table.setHorizontalHeaderLabels(["Mensaje"])
                msg_item = QTableWidgetItem("Por favor, agrega una moneda.")
                self.monitoring_table.setItem(0, 0, msg_item)

                # Botón para llevar a la sección de búsqueda
                add_coin_button = QPushButton("Agregar moneda")
                add_coin_button.clicked.connect(
                    lambda: self.tab_widget.setCurrentIndex(1))  # Ir a la pestaña de búsqueda
                self.monitoring_table.setCellWidget(0, 0, add_coin_button)
                return

            # Caso 4: Hay monedas e indicadores
            num_columns = 4 + len(self.indicators) + 1  # Moneda, Acción, Indicadores, Tendencia, Agregar Indicador
            self.monitoring_table.setRowCount(len(self.coins))
            self.monitoring_table.setColumnCount(num_columns)

            # Configuración de cabeceras
            header_labels = ["", "", "Moneda"] + [f"{ind['name']} ({ind['timeframe']})" for ind in self.indicators] + [
                "Tendencia", "Agregar Indicador"]
            self.monitoring_table.setHorizontalHeaderLabels(header_labels)

            for row, coin in enumerate(self.coins):
                # Botón de eliminar
                delete_button = QPushButton()
                delete_button.setIcon(qta.icon("mdi.delete"))
                delete_button.clicked.connect(lambda _, r=row: self.remove_coin(r))
                self.monitoring_table.setCellWidget(row, 0, delete_button)

                # Botón para abrir web
                web_button = QPushButton()
                web_button.setIcon(qta.icon("mdi.web"))
                web_button.clicked.connect(lambda _, c=coin["name"]: self.open_web_page(c))
                self.monitoring_table.setCellWidget(row, 1, web_button)

                # Nombre de la moneda
                self.monitoring_table.setItem(row, 2, QTableWidgetItem(coin["name"]))

                # Cálculo de indicadores
                indicator_states = []
                for col, indicator in enumerate(self.indicators, start=3):
                    interval = self.map_interval(indicator["timeframe"])
                    if not interval:
                        self.monitoring_table.setItem(row, col, QTableWidgetItem("Intervalo Inválido"))
                        indicator_states.append("Error")
                        continue

                    coin_data = self.fetch_historical_data(coin["name"], interval)
                    if coin_data is None or coin_data.empty:
                        self.monitoring_table.setItem(row, col, QTableWidgetItem("Error"))
                        indicator_states.append("Error")
                        continue

                    if indicator["name"] == "EMA":
                        period = int(indicator["parameters"].split(": ")[1])
                        ema = ta.ema(coin_data["close"], length=period)
                        state = "Alcista" if coin_data["close"].iloc[-1] > ema.iloc[-1] else "Bajista"
                    elif indicator["name"] == "MACD":
                        fast, slow, signal = map(int, [x.split(": ")[1] for x in indicator["parameters"].split(", ")])
                        macd = ta.macd(coin_data["close"], fast=fast, slow=slow, signal=signal)
                        state = "Alcista" if macd["MACD_12_26_9"].iloc[-1] > macd["MACDs_12_26_9"].iloc[
                            -1] else "Bajista"
                    else:
                        state = "Error"

                    self.monitoring_table.setItem(row, col, QTableWidgetItem(state))
                    indicator_states.append(state)

                # Determinar tendencia general
                if all(state == "Alcista" for state in indicator_states):
                    trend = "Alcista"
                elif all(state == "Bajista" for state in indicator_states):
                    trend = "Bajista"
                else:
                    trend = "Neutral"

                # Mostrar tendencia
                self.monitoring_table.setItem(row, num_columns - 2, QTableWidgetItem(trend))

                # Alerta visual y sonora solo para "Alcista" o "Bajista"
                if trend in ["Alcista", "Bajista"]:
                    alert_message = f"La tendencia para {coin['name']} es {trend}."
                    QMessageBox.information(self, "Alerta de Tendencia", alert_message)
                    sound_file = "alert.wav"  # Ruta al archivo de sonido
                    play_sound(sound_file)

                # Botón para agregar indicador (solo si hay menos de 6 indicadores)
                if len(self.indicators) < 6:
                    add_indicator_button = QPushButton("Agregar indicador")
                    add_indicator_button.clicked.connect(
                        lambda: self.tab_widget.setCurrentIndex(2))  # Ir a configuración
                    self.monitoring_table.setCellWidget(row, num_columns - 1, add_indicator_button)
                else:
                    max_label = QLabel("Máximo alcanzado")
                    max_label.setAlignment(Qt.AlignCenter)
                    self.monitoring_table.setCellWidget(row, num_columns - 1, max_label)


        except Exception as e:
            self.show_message("Error", f"Se produjo un error al actualizar la tabla: {str(e)}")

    def fetch_historical_data(self, coin, interval):
        try:
            url = f"https://contract.mexc.com/api/v1/contract/kline/{coin}?interval={interval}&limit=500"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and "data" in data:
                    df = pd.DataFrame({
                        "timestamp": data["data"]["time"],
                        "close": data["data"]["close"]
                    })
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit='s')
                    df["close"] = df["close"].astype(float)
                    return df
            return None
        except Exception as e:
            return None

    def add_coin_to_monitoring(self, coin):
        if coin not in [c["name"] for c in self.coins]:
            self.coins.append({"name": coin, "trend": "Neutral"})
            self.update_table()
            self.save_coins_to_file()  # Guardar monedas
            self.show_message("Éxito", f"La moneda {coin} fue agregada al monitoreo.")
        else:
            self.show_message("Información", f"La moneda {coin} ya está en monitoreo.")

    def remove_coin(self, row):
        confirm = QMessageBox.question(
            self,
            "Confirmación",
            "¿Estás seguro de que deseas eliminar esta moneda?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.coins.pop(row)
            self.update_table()
            self.save_coins_to_file()  # Guardar monedas

    def save_coins_to_file(self):
        try:
            with open("coins.json", "w") as file:
                json.dump(self.coins, file)
        except Exception as e:
            self.show_message("Error", f"No se pudo guardar las monedas: {e}")

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
            self.indicators.pop(row)
            self.update_indicator_table()
            self.save_indicators_to_file()
            self.update_table()

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

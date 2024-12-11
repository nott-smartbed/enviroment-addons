import os
import time
import json
import requests
from library.bmp280_driver import BMP280
from smbus2 import SMBus
from Adafruit_BMP.BMP085 import BMP085
from library.DFRobot_Oxygen import DFRobot_Oxygen_IIC
from library.SHT4x import SHT4x

class SensorManager:
    def __init__(self, options_path="/data/options.json"):
        # Đọc các tùy chọn từ file options.json
        self.options = self.load_options(options_path)

        # Lấy thông tin cấu hình của Home Assistant từ Supervisor API
        self.ha_base_url = "http://supervisor/core/api"
        self.ha_token = os.getenv("SUPERVISOR_TOKEN")

        self.validate_config()

        # Khởi tạo headers cho việc gửi dữ liệu lên Home Assistant
        self.headers = {
            "Authorization": f"Bearer {self.ha_token}",
            "Content-Type": "application/json",
        }

        # Khởi tạo bus I2C
        self.bus = SMBus(5)  # Điều chỉnh bus I2C nếu cần thiết

        # Khởi tạo các cảm biến nếu chúng được bật trong cấu hình
        if self.options.get("bmp180", False):
            self.bmp180 = BMP085(busnum=5)  # BMP180
        if self.options.get("bmp280", False):
            self.bmp280 = BMP280(i2c_addr=int(self.options.get("addr-bmp", "0x76"), 16), i2c_dev=self.bus)
            self.bmp280.setup(
                mode="normal",
                temperature_oversampling=16,
                pressure_oversampling=16,
                temperature_standby=500
            )
        if self.options.get("oxygen", False):
            self.oxygen_sensor = DFRobot_Oxygen_IIC(5, int(self.options.get("addr-oxy", "0x73"), 16))
        if self.options.get("sht31", False):
            self.sht31_address = int(self.options.get("addr-sht", "0x44"), 16)
            self.read_temp_hum_cmd = [0x2C, 0x06]
        if self.options.get("sht45", False):
            self.sht45_sensor = SHT4x(bus=5, address=0x44, mode="high")

    def load_options(self, file_path):
        try:
            with open(file_path, "r") as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading options: {e}")
            return {}

    def validate_config(self):
        if not self.ha_token:
            print("Error: Supervisor token is missing.")
            exit(1)

    def post_to_home_assistant(self, sensor_name, value, unit, friendly_name):
        url = f"{self.ha_base_url}/states/sensor.{sensor_name}"
        payload = {
            "state": value,
            "attributes": {
                "unit_of_measurement": unit,
                "friendly_name": friendly_name,
            },
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            print(f"Data posted to {sensor_name}: {value}{unit}")
        except requests.exceptions.RequestException as e:
            print(f"Error posting to Home Assistant: {e}")

    def read_sht31(self):
        try:
            self.bus.write_i2c_block_data(self.sht31_address, self.read_temp_hum_cmd[0], self.read_temp_hum_cmd[1:])
            time.sleep(0.5)
            data = self.bus.read_i2c_block_data(self.sht31_address, 0x00, 6)
            temp_raw = (data[0] << 8) + data[1]
            humidity_raw = (data[3] << 8) + data[4]
            temperature = -45 + (175 * temp_raw / 65535.0)
            humidity = (100 * humidity_raw / 65535.0)
            return temperature, humidity
        except Exception as e:
            print(f"Error reading SHT31: {e}")
            return None, None

    def read_sht45(self):
        try:
            self.sht45_sensor.update()
            temperature = self.sht45_sensor.temperature
            humidity = self.sht45_sensor.humidity
            return temperature, humidity
        except Exception as e:
            print(f"Error reading SHT45: {e}")
            return None, None

    def read_oxygen(self):
        try:
            oxygen_concentration = self.oxygen_sensor.get_oxygen_data(collect_num=20)
            return oxygen_concentration
        except Exception as e:
            print(f"Error reading Oxygen sensor: {e}")
            return None

    def run(self):
        while True:
            # Đọc và gửi dữ liệu từ BMP180
            if self.options.get("bmp180", False):
                try:
                    pressure = self.bmp180.read_pressure()
                    self.post_to_home_assistant("bmp180_pressure", round(pressure / 100, 2), "hPa", "BMP180 Pressure")
                except Exception as e:
                    print(f"Error reading BMP180: {e}")

            # Đọc và gửi dữ liệu từ BMP280
            if self.options.get("bmp280", False):
                try:
                    temperature = self.bmp280.get_temperature()
                    pressure = self.bmp280.get_pressure()
                    self.post_to_home_assistant("bmp280_temperature", round(temperature, 2), "°C", "BMP280 Temperature")
                    self.post_to_home_assistant("bmp280_pressure", round(pressure, 2), "hPa", "BMP280 Pressure")
                except Exception as e:
                    print(f"Error reading BMP280: {e}")

            # Đọc và gửi dữ liệu từ SHT31
            if self.options.get("sht31", False):
                try:
                    temperature, humidity = self.read_sht31()
                    if temperature is not None and humidity is not None:
                        self.post_to_home_assistant("sht31_temperature", round(temperature, 2), "°C", "SHT31 Temperature")
                        self.post_to_home_assistant("sht31_humidity", round(humidity, 2), "%", "SHT31 Humidity")
                except Exception as e:
                    print(f"Error reading SHT31: {e}")

            # Đọc và gửi dữ liệu từ SHT45
            if self.options.get("sht45", False):
                try:
                    temperature, humidity = self.read_sht45()
                    if temperature is not None and humidity is not None:
                        self.post_to_home_assistant("sht45_temperature", round(temperature, 2), "°C", "SHT45 Temperature")
                        self.post_to_home_assistant("sht45_humidity", round(humidity, 2), "%", "SHT45 Humidity")
                except Exception as e:
                    print(f"Error reading SHT45: {e}")

            # Đọc và gửi dữ liệu từ cảm biến Oxy
            if self.options.get("oxygen", False):
                try:
                    oxygen_concentration = self.read_oxygen()
                    if oxygen_concentration is not None:
                        self.post_to_home_assistant("oxygen_concentration", round(oxygen_concentration, 2), "%", "Oxygen Concentration")
                except Exception as e:
                    print(f"Error reading Oxygen sensor: {e}")

            time.sleep(10)

if __name__ == "__main__":
    sensor_manager = SensorManager()
    sensor_manager.run()


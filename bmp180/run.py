from Adafruit_BMP.BMP085 import BMP085
import requests
import json
import time
def load_options(file_path="/data/options.json"):
    try:
        with open(file_path, "r") as file:
            options = json.load(file)
            return options
    except FileNotFoundError:
        print(f"Error: {file_path} not found!")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return {}
options = load_options()
HA_BASE_URL = options.get("api_base_url", "http://default-url")
HA_TOKEN = options.get("api_token", "default-token")

# Kiểm tra nếu thiếu cấu hình cần thiết
if HA_BASE_URL == "http://default-url" or HA_TOKEN == "default-token":
    print("Error: Missing required configuration in options.json.")
    exit(1)

# Thiết lập header cho API
HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

# URL cho từng cảm biến
TEMP_SENSOR_URL = f"{HA_BASE_URL}/sensor.bmp180_temperature"
PRESSURE_SENSOR_URL = f"{HA_BASE_URL}/sensor.bmp180_pressure"
# Khởi tạo cảm biến trên bus 5
def post_to_home_assistant(url, payload):
    try:
        response = requests.post(url, json=payload, headers=HEADERS)
        response.raise_for_status()  # Kích hoạt ngoại lệ nếu có lỗi HTTP
        print(f"Data posted to {url}: {payload}")
    except requests.exceptions.RequestException as e:
        print(f"Error posting to Home Assistant: {e}")
sensor = BMP085(busnum=5)

while True:
    # Đọc dữ liệu từ cảm biến
    temperature = sensor.read_temperature()  # Nhiệt độ (°C)
    pressure = sensor.read_pressure()        # Áp suất (Pa)

    # Gửi dữ liệu nhiệt độ
    temperature_payload = {
        "state": round(temperature, 2),
        "attributes": {
            "unit_of_measurement": "°C",
            "friendly_name": "Temperature",
        },
    }
    post_to_home_assistant(TEMP_SENSOR_URL, temperature_payload)

    # Gửi dữ liệu áp suất
    pressure_payload = {
        "state": round(pressure, 2),
        "attributes": {
            "unit_of_measurement": "Pa",
            "friendly_name": "Pressure",
        },
    }
    post_to_home_assistant(PRESSURE_SENSOR_URL, pressure_payload)

    # In dữ liệu ra màn hình
    print(f"Nhiệt độ: {temperature:.2f} °C")
    print(f"Áp suất: {pressure:.2f} Pa")
    print("-------------------------------")

    # Chờ 10 giây trước khi đo lại
    time.sleep(10)

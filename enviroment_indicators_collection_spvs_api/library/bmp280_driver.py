"""BMP280/BME280 Driver."""

import struct
import time
from i2cdevice import BitField, Device, Register, _int_to_bytes
from i2cdevice.adapter import Adapter, LookupAdapter

__version__ = "1.0.1"

BMP280_CHIP_ID = 0x58
BME280_CHIP_ID = 0x60
I2C_ADDRESS_GND = 0x76
I2C_ADDRESS_VCC = 0x77


class S16Adapter(Adapter):
    """Convert unsigned 16bit integer to signed."""

    def _decode(self, value):
        return struct.unpack("<h", _int_to_bytes(value, 2))[0]


class U16Adapter(Adapter):
    """Convert from bytes to an unsigned 16bit integer."""

    def _decode(self, value):
        return struct.unpack("<H", _int_to_bytes(value, 2))[0]


class BMP280Calibration:
    def __init__(self):
        self.dig_t1 = 0
        self.dig_t2 = 0
        self.dig_t3 = 0
        self.dig_p1 = 0
        self.dig_p2 = 0
        self.dig_p3 = 0
        self.dig_p4 = 0
        self.dig_p5 = 0
        self.dig_p6 = 0
        self.dig_p7 = 0
        self.dig_p8 = 0
        self.dig_p9 = 0
        self.temperature_fine = 0

    def set_from_namedtuple(self, value):
        for key in self.__dict__.keys():
            try:
                setattr(self, key, getattr(value, key))
            except AttributeError:
                pass

    def compensate_temperature(self, raw_temperature):
        var1 = (raw_temperature / 16384.0 - self.dig_t1 / 1024.0) * self.dig_t2
        var2 = (raw_temperature / 131072.0 - self.dig_t1 / 8192.0) ** 2 * self.dig_t3
        self.temperature_fine = var1 + var2
        return self.temperature_fine / 5120.0

    def compensate_pressure(self, raw_pressure):
        var1 = self.temperature_fine / 2.0 - 64000.0
        var2 = var1 ** 2 * self.dig_p6 / 32768.0
        var2 += var1 * self.dig_p5 * 2
        var2 = var2 / 4.0 + self.dig_p4 * 65536.0
        var1 = (self.dig_p3 * var1 ** 2 / 524288.0 + self.dig_p2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * self.dig_p1
        if var1 == 0:
            return 0  # Avoid division by zero
        pressure = 1048576.0 - raw_pressure
        pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
        var1 = self.dig_p9 * pressure ** 2 / 2147483648.0
        var2 = pressure * self.dig_p8 / 32768.0
        return pressure + (var1 + var2 + self.dig_p7) / 16.0


class BMP280:
    def __init__(self, i2c_addr=I2C_ADDRESS_GND, i2c_dev=None):
        self.calibration = BMP280Calibration()
        self._is_setup = False
        self._i2c_addr = i2c_addr
        self._i2c_dev = i2c_dev
        self._bmp280 = Device([I2C_ADDRESS_GND, I2C_ADDRESS_VCC], i2c_dev=self._i2c_dev, bit_width=8, registers=(
            Register("CHIP_ID", 0xD0, fields=(BitField("id", 0xFF),)),
            Register("RESET", 0xE0, fields=(BitField("reset", 0xFF),)),
            Register("STATUS", 0xF3, fields=(
                BitField("measuring", 0b00001000),
                BitField("im_update", 0b00000001),
            )),
            Register("CTRL_MEAS", 0xF4, fields=(
                BitField("osrs_t", 0b11100000, adapter=LookupAdapter({
                    1: 0b001,
                    2: 0b010,
                    4: 0b011,
                    8: 0b100,
                    16: 0b101,
                })),
                BitField("osrs_p", 0b00011100, adapter=LookupAdapter({
                    1: 0b001,
                    2: 0b010,
                    4: 0b011,
                    8: 0b100,
                    16: 0b101,
                })),
                BitField("mode", 0b00000011, adapter=LookupAdapter({
                    "sleep": 0b00,
                    "forced": 0b10,
                    "normal": 0b11,
                })),
            )),
            Register("CONFIG", 0xF5, fields=(
                BitField("t_sb", 0b11100000, adapter=LookupAdapter({
                    0.5: 0b000,
                    62.5: 0b001,
                    125: 0b010,
                    250: 0b011,
                    500: 0b100,
                    1000: 0b101,
                    2000: 0b110,
                    4000: 0b111,
                })),
                BitField("filter", 0b00011100),
                BitField("spi3w_en", 0b00000001, read_only=True),
            )),
            Register("DATA", 0xF7, fields=(
                BitField("temperature", 0x000000FFFFF0),
                BitField("pressure", 0xFFFFF0000000),
            ), bit_width=48),
            Register("CALIBRATION", 0x88, fields=(
                BitField("dig_t1", 0xFFFF << 16 * 11, adapter=U16Adapter()),
                BitField("dig_t2", 0xFFFF << 16 * 10, adapter=S16Adapter()),
                BitField("dig_t3", 0xFFFF << 16 * 9, adapter=S16Adapter()),
                BitField("dig_p1", 0xFFFF << 16 * 8, adapter=U16Adapter()),
                BitField("dig_p2", 0xFFFF << 16 * 7, adapter=S16Adapter()),
                BitField("dig_p3", 0xFFFF << 16 * 6, adapter=S16Adapter()),
                BitField("dig_p4", 0xFFFF << 16 * 5, adapter=S16Adapter()),
                BitField("dig_p5", 0xFFFF << 16 * 4, adapter=S16Adapter()),
                BitField("dig_p6", 0xFFFF << 16 * 3, adapter=S16Adapter()),
                BitField("dig_p7", 0xFFFF << 16 * 2, adapter=S16Adapter()),
                BitField("dig_p8", 0xFFFF << 16 * 1, adapter=S16Adapter()),
                BitField("dig_p9", 0xFFFF << 16 * 0, adapter=S16Adapter()),
            ), bit_width=192)
        ))

    def setup(self, mode="normal", temperature_oversampling=16, pressure_oversampling=16, temperature_standby=500):
        if self._is_setup:
            return
        self._is_setup = True

        self._bmp280.select_address(self._i2c_addr)
        self._mode = mode

        if mode == "forced":
            mode = "sleep"

        try:
            chip = self._bmp280.get("CHIP_ID")
            if chip.id not in [BMP280_CHIP_ID, BME280_CHIP_ID]:
                raise RuntimeError(f"Unable to find BMP280/BME280 on 0x{self._i2c_addr:02x}, CHIP_ID returned {chip.id:02x}")
        except IOError:
            raise RuntimeError(f"Unable to find BMP280/BME280 on 0x{self._i2c_addr:02x}, IOError")

        self._bmp280.set("CTRL_MEAS", mode=mode, osrs_t=temperature_oversampling, osrs_p=pressure_oversampling)
        self._bmp280.set("CONFIG", t_sb=temperature_standby, filter=2)
        self.calibration.set_from_namedtuple(self._bmp280.get("CALIBRATION"))

    def update_sensor(self):
        self.setup()
        if self._mode == "forced":
            self._bmp280.set("CTRL_MEAS", mode="forced")
            while self._bmp280.get("STATUS").measuring:
                time.sleep(0.001)
        raw = self._bmp280.get("DATA")
        self.temperature = self.calibration.compensate_temperature(raw.temperature)
        self.pressure = self.calibration.compensate_pressure(raw.pressure) / 100.0

    def get_temperature(self):
        self.update_sensor()
        return self.temperature

    def get_pressure(self):
        self.update_sensor()
        return self.pressure

    def get_altitude(self, qnh=1013.25, manual_temperature=None):
        self.update_sensor()
        pressure = self.get_pressure()
        temperature = manual_temperature if manual_temperature else self.get_temperature()
        altitude = ((pow((qnh / pressure), (1.0 / 5.257)) - 1) * (temperature + 273.15)) / 0.0065
        return altitude


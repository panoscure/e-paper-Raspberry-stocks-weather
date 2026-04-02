#!/usr/bin/env python3
"""
Driver for Waveshare 7.5" V2 e-Paper display.
Provides RaspberryPi hardware abstraction and EPD control class.
"""

import logging
import time
from contextlib import contextmanager

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import spidev
import gpiozero

logger = logging.getLogger(__name__)

# Display dimensions
EPD_WIDTH = 800
EPD_HEIGHT = 480


def _sleep_ms(ms):
    """Sleep for milliseconds."""
    time.sleep(ms / 1000)


class RaspberryPi:
    """Hardware abstraction for Raspberry Pi GPIO and SPI."""
    # Pin definition (BCM)
    RST_PIN = 17
    DC_PIN = 25
    CS_PIN = 8
    BUSY_PIN = 24
    PWR_PIN = 18
    MOSI_PIN = 10
    SCLK_PIN = 11

    def __init__(self):
        self.SPI = spidev.SpiDev()
        self.GPIO_RST_PIN = gpiozero.LED(self.RST_PIN)
        self.GPIO_DC_PIN = gpiozero.LED(self.DC_PIN)
        self.GPIO_PWR_PIN = gpiozero.LED(self.PWR_PIN)
        self.GPIO_BUSY_PIN = gpiozero.Button(self.BUSY_PIN, pull_up=False)

    def digital_write(self, pin, value):
        if pin == self.RST_PIN:
            if value:
                self.GPIO_RST_PIN.on()
            else:
                self.GPIO_RST_PIN.off()
        elif pin == self.DC_PIN:
            if value:
                self.GPIO_DC_PIN.on()
            else:
                self.GPIO_DC_PIN.off()

    def digital_read_busy(self):
        return self.GPIO_BUSY_PIN.value

    def spi_writebytes(self, data):
        self.SPI.writebytes(data)

    def spi_writebytes2(self, data):
        self.SPI.writebytes2(data)

    def module_init(self):
        self.GPIO_PWR_PIN.on()
        self.SPI.open(0, 0)
        self.SPI.max_speed_hz = 4000000
        self.SPI.mode = 0b00

    def module_exit(self):
        logger.debug("spi end")
        self.SPI.close()
        self.GPIO_RST_PIN.off()
        self.GPIO_DC_PIN.off()
        self.GPIO_PWR_PIN.off()


class EPD:
    """Waveshare 7.5" V2 e-Paper display driver."""

    def __init__(self, epdcfg):
        self.epdcfg = epdcfg
        self.width = EPD_WIDTH
        self.height = EPD_HEIGHT

    def reset(self):
        self.epdcfg.digital_write(self.epdcfg.RST_PIN, 1)
        _sleep_ms(20)
        self.epdcfg.digital_write(self.epdcfg.RST_PIN, 0)
        _sleep_ms(2)
        self.epdcfg.digital_write(self.epdcfg.RST_PIN, 1)
        _sleep_ms(20)

    def _send_command(self, command):
        self.epdcfg.digital_write(self.epdcfg.DC_PIN, 0)
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 0)
        self.epdcfg.spi_writebytes((command,))
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 1)

    def _send_data(self, data):
        self.epdcfg.digital_write(self.epdcfg.DC_PIN, 1)
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 0)
        self.epdcfg.spi_writebytes((data,))
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 1)

    def _send_data2(self, data):
        self.epdcfg.digital_write(self.epdcfg.DC_PIN, 1)
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 0)
        self.epdcfg.spi_writebytes2(data)
        self.epdcfg.digital_write(self.epdcfg.CS_PIN, 1)

    def _read_busy(self):
        logger.debug("e-Paper busy")
        self._send_command(0x71)
        busy = self.epdcfg.digital_read_busy()
        n = 1
        while busy == 0:
            n += 1
            _sleep_ms(10)
            self._send_command(0x71)
            busy = self.epdcfg.digital_read_busy()
        _sleep_ms(20)
        logger.debug(f"e-Paper busy release, checked {n} times")

    def _init(self):
        self.epdcfg.module_init()
        self.reset()

        self._send_command(0x06)  # btst
        self._send_data(0x17)
        self._send_data(0x17)
        self._send_data(0x28)
        self._send_data(0x17)

        self._send_command(0x01)  # POWER SETTING
        self._send_data(0x07)
        self._send_data(0x07)
        self._send_data(0x28)
        self._send_data(0x17)

        self._send_command(0x04)  # POWER ON
        _sleep_ms(100)
        self._read_busy()

        self._send_command(0x00)  # PANNEL SETTING
        self._send_data(0x1F)

        self._send_command(0x61)  # tres
        self._send_data(0x03)
        self._send_data(0x20)
        self._send_data(0x01)
        self._send_data(0xE0)

        self._send_command(0x15)
        self._send_data(0x00)

        self._send_command(0x50)
        self._send_data(0x10)
        self._send_data(0x07)

        self._send_command(0x60)  # TCON SETTING
        self._send_data(0x22)

    def clear(self):
        self._init()
        self._send_command(0x10)
        self._send_data2([0xFF] * (self.width * self.height // 8))
        self._send_command(0x13)
        self._send_data2([0x00] * (self.width * self.height // 8))

        self._send_command(0x12)
        _sleep_ms(3500)
        self._read_busy()

    def display_image(self, image: Image.Image):
        if image.mode != '1':
            image = image.convert('1')
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height))

        data = image.tobytes()
        self._send_command(0x10)
        self._send_data2(data)

        data_inv = ~np.frombuffer(data, dtype=np.uint8)
        self._send_command(0x13)
        self._send_data2(data_inv)

        self._send_command(0x12)
        _sleep_ms(3000)
        self._read_busy()

    def sleep(self):
        self._send_command(0x50)
        self._send_data(0xF7)

        self._send_command(0x02)  # POWER_OFF
        self._read_busy()

        self._send_command(0x07)  # DEEP_SLEEP
        self._send_data(0xA5)

        _sleep_ms(2000)
        self.epdcfg.module_exit()

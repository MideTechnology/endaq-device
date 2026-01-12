"""
These are commands to interface with the Raspi_Endaq_Controller_Relay board from the Raspi.
There are a few different test boards, so make sure you're using the right one
"""
import subprocess
import time
from abc import ABC, abstractmethod

class HardwareInterface(ABC):
    @abstractmethod
    def set_usb(self, on: bool) -> None:
        pass

    @abstractmethod
    def set_button(self, on: bool) -> None:
        pass

    @abstractmethod
    def timed_button_press(self, period: int) -> None:
        pass

class FakeInterface(HardwareInterface):
    def set_usb(self, on: bool) -> None:
        pass

    def set_button(self, on: bool) -> None:
        pass

    def timed_button_press(self, period: int) -> None:
        pass

class WindowsInterface(HardwareInterface):
    def set_usb(self, on: bool) -> None:
        if on:
            input("Connect test unit to USB and press Enter")
        else:
            input("Disconnect device from USB and press Enter")

    def set_button(self, on: bool) -> None:
        pass        

    def timed_button_press(self, period: int) -> None:
        input(f"Press button for {period} seconds and press Enter")


class RaspiInterface(HardwareInterface):
    usb_state: bool
    button_state: bool

    def __init__(self):
        print(f"Initing a Raspi interface")
        usb_state = True
        button_state = True

    def set_usb(self, on: bool) -> None:
        """
        Command Raspi to connect or disconnect USB
        
        :param on: True to connect USB, False to disconnect USB
        :type on: bool
        """
        self._set_line(27, on)

    def set_button(self, on: bool):
        """
        Docstring for set_button
        
        :param on: True to "press" (ground) button, False to float it
        :type on: bool
        """
        self._set_line(16, on)

    def timed_button_press(self, period: int):
        """
        "Press" button for period seconds
        
        :param period: Number of seconds to press button
        :type period: int
        """
        self.set_button(True)
        time.sleep(period)
        self.set_button(False)

    def _set_line(self, line: int, value: bool):
        """
        Interface to set a Raspi GPIO
        
        :param line: GPIO number (note: NOT the pin number the GPIO number)
        :type line: int
        :param value: True to drive line high, False to drive low
        :type value: bool
        """
        if value == True:
            line_value = 1
        else:
            line_value = 0
        try:
            res = subprocess.run(['gpioset', 'gpiochip0', f"{line}={line_value}"], capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Command failed with exit code {e.returncode}")
            print("STDOUT:", e.stdout)
            print("STDERR:", e.stderr)
            raise e


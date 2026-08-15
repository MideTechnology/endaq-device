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
        
    @abstractmethod
    def unplug_replug(self, period: int) -> None:
        pass

class MockInterface(HardwareInterface):
    def set_usb(self, on: bool) -> None:
        pass

    def set_button(self, on: bool) -> None:
        pass

    def timed_button_press(self, period: int) -> None:
        pass

    def unplug_replug(self, period: int) -> None:
        pass

class TTYInterface(HardwareInterface):
    def set_usb(self, on: bool) -> None:
        if on:
            input("Connect test unit to USB and press Enter")
        else:
            input("Disconnect device from USB and press Enter")

    def set_button(self, on: bool) -> None:
        pass        

    def timed_button_press(self, period: int) -> None:
        if period <= 0.5:
            input(f"click button and press Enter")
        else:
            input(f"Press button for {period} seconds and press Enter")

    def unplug_replug(self, period: int) -> None:
        self.set_usb(False)
        time.sleep(period)
        self.set_usb(True)
        time.sleep(period)


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

    def unplug_replug(self, period: int) -> None:
        self.set_usb(False)
        time.sleep(period)
        self.set_usb(True)
        time.sleep(period)
        
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

class NoInteractInterface(HardwareInterface):
    """

    """

    _exc_type: Exception

    def __init__(self, exc_type):
        """
        
        :param exc_type: an exception / error type that will be called when 
            the interface was attempted to be called upon

        """
        self._exc_type = exc_type

    def set_usb(self, on: bool) -> None:
        raise self._exc_type(f"set_usb {on} was called against a NoInteractInterface")

    def set_button(self, on: bool) -> None:
        raise self._exc_type(f"set_button {on} was called against a NoInteractInterface")

    def timed_button_press(self, period: int) -> None:
        raise self._exc_type(f"timed_button_press {period} was called against a NoInteractInterface")

    def unplug_replug(self, period: int) -> None:
        raise self._exc_type(f"unplug_replug {period} was called against a NoInteractInterface")


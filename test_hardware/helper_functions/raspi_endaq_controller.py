"""
These are commands to interface with the Raspi_Endaq_Controller_Relay board from the Raspi.
There are a few different test boards, so make sure you're using the right one, this is the hat that sits on top of the Raspi
"""
import subprocess
import time

def _set_line(line: int, value: bool):
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

def set_usb(on: bool):
    """
    Command Raspi to connect or disconnect USB
    
    :param on: True to connect USB, False to disconnect USB
    :type on: bool
    """
    _set_line(27, on)

def set_button(on: bool):
    """
    Docstring for set_button
    
    :param on: True to "press" (ground) button, False to float it
    :type on: bool
    """
    _set_line(16, on)

def _handle_usb(state: str):
    """
    Handle command line input to turn USB on or off
    
    :param state: "on" to turn USB on, "off" to disconnect USB
    :type state: str
    """
    state = state.lower()
    if state not in ['on', 'off']:
        print("State must be either 'on' or 'off'")
        exit(1)
    set_usb(state == 'on')

def timed_button_press(period: int):
    """
    "Press" button for period seconds
    
    :param period: Number of seconds to press button
    :type period: int
    """
    set_button(True)
    time.sleep(period)
    set_button(False)


def _handle_button(state: str):
    """
    Handle command line input to set the button to on, off, or on for a defined number of seconds
    
    :param state: "on" or "off" to set the button, or a string formatted integer to press for number of seconds
    :type state: str
    """
    if state.isalpha():
        state = state.lower()
        if state not in ['on', 'off']:
            print("State must be either 'on' or 'off'")
            exit(1)
        set_button(state == 'on')
        return
    on_time = int(state)
    timed_button_press(on_time)

def _connect_device(try_time: int) -> bool:
    """
    Try for 'time' seconds to connect to a device, return True if found, False otherwise
    
    :param time: Time to wait for connection
    :type time: int
    :return: True if device is found, False otherwise
    :rtype: bool
    """
    import endaq.device as ed

    start_time = time.time()
    while time.time() - start_time < try_time:
        devs = ed.getDevices(unmounted=False)
        if len(devs):
            print(f"After {time.time() - start_time} seconds we found {devs}")
            return True
    return False



if __name__ == '__main__':
    import argparse
    import os
    argparser = argparse.ArgumentParser("Tool for interfacing with the Raspi enDAQ Controller")
    argparser.add_argument('-u', '--usb',
                           default=os.getenv("USB", None),
                           help="State for the USB, on or off")
    argparser.add_argument('-b', '--button',
                           default=os.getenv("BUTTON", None),
                           help="State for the button, string of on or off, or a number for a time in seconds to go on")
    argparser.add_argument('-c', '--connect', 
                           default=int(os.getenv("CONNECT_TIME", 0)),
                           type=int,                           
                           help="If set, script will try for 'connect' seconds to connect to the device, and error out if no device is found.")
    argparser.add_argument('-r', '--retry', action="store_true", 
                           help="If set, if the connect fails, script will try to reset the device with a 20 second button press and connect again, once")
    args = argparser.parse_args()

    if os.getenv("RETRY", "false").lower() == "true":
        args.retry = True

    print(f"{args}")

    if args.usb is not None:
        _handle_usb(args.usb)
    if args.button is not None:
        _handle_button(args.button)
    if args.connect:
        if _connect_device(args.connect) == False:
            if args.retry:
                print(f"Initial connection failed, using retry")
                timed_button_press(20)
                if _connect_device(args.connect) == False:
                    raise ConnectionError(f"Could not connect to USB device after retry. Call settings = {args=}")
            else:
                raise ConnectionError(f"Could not connect to USB device. Call settings = {args=}")
        

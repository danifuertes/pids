import time
from robomaster import robot


def connect(connection='networking'):
    """
    Connect to RoboMaster using networking mode. You must first run the \
        connect.py script and scan the QR code with the robot. A txt named \
        'serial_number.txt' should exist and contain the serial number of \
        the robot.
    :param image: type of connection. Options are: 'networking' (Router), 'wifi' (Wi-Fi), 'usb' (USB).
    :return:
        ep_robot: RoboMaster object with connection established.
    """
    mapping = {'networking': 'sta', 'wifi': 'ap', 'usb': 'rndis'}

    # Get serial number
    if connection == 'networking':
        with open('serial_number.txt', 'r') as f:
            SERIAL_NUMBER = f.read()
    else:
        SERIAL_NUMBER = None

    # Start connection
    ep_robot = robot.Robot()
    ep_robot.initialize(conn_type=mapping[connection], sn=SERIAL_NUMBER)
    return ep_robot


def sub_info_handler(batter_info, ep_robot_):
    # Print remaining battery percentage
    percent = batter_info
    print(f'Battery: {percent}%.')

    # Led module
    ep_led = ep_robot_.led

    # Indicate the battery level with the brightness of the LED
    brightness = int(percent * 255 / 100)
    ep_led.set_led(comp="all", r=brightness, g=brightness, b=brightness)


if __name__ == '__main__':
    
    # Connect the robot
    ep_robot = connect()

    # Battery module
    ep_battery = ep_robot.battery

    # Subscribe to battery info with a callback
    ep_battery.sub_battery_info(1, sub_info_handler, ep_robot)
    time.sleep(1)

    # Unsubscribe to battery info
    ep_battery.unsub_battery_info()

    # End connection
    ep_robot.close()

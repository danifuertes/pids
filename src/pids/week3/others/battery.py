import time
from robomaster import robot


def connect(connection='networking'):
    """Connect to the RoboMaster and return the robot object.

    Run connect.py once and scan the QR code so the robot joins your network.
    In 'networking' mode the robot is found by the serial number saved in
    'serial_number.txt' (created by connect.py).
    :param connection: 'networking' (router), 'wifi' (direct Wi-Fi) or 'usb'.
    :return: ep_robot, a connected RoboMaster object.
    """
    conn_types = {'networking': 'sta', 'wifi': 'ap', 'usb': 'rndis'}

    # In networking mode the robot is identified by its serial number
    serial_number = None
    if connection == 'networking':
        with open('serial_number.txt', 'r') as f:
            serial_number = f.read()

    # Start the connection
    ep_robot = robot.Robot()
    ep_robot.initialize(conn_type=conn_types[connection], sn=serial_number)
    return ep_robot


def sub_info_handler(percent, ep_robot):
    """Print the battery level and mirror it on the LED brightness (callback)."""
    print(f'Battery: {percent}%.')

    # Light all LEDs proportionally to the remaining charge (0-255)
    brightness = int(percent * 255 / 100)
    ep_robot.led.set_led(comp="all", r=brightness, g=brightness, b=brightness)


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

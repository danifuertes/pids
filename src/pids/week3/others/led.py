import time
from robomaster import robot, led


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


if __name__ == '__main__':
    
    # Connect the robot
    ep_robot = connect()

    # Led module
    ep_led = ep_robot.led

    # Set the lighting effect to always be on and the brightness increases
    bright = 1
    for i in range(0, 8):
        ep_led.set_led(
            comp=led.COMP_ALL,
            r=bright << i,
            g=bright << i,
            b=bright << i,
            effect=led.EFFECT_ON
        )
        time.sleep(1)
        print(f'brightness: {bright << i}')

    # Set the color (it will remain after the code execution)
    ep_led.set_led(
        comp=led.COMP_ALL,
        r=155,
        g=0,
        b=255,
    )

    # End connection
    ep_robot.close()

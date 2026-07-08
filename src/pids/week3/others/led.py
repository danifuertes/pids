import time
from robomaster import robot, led


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

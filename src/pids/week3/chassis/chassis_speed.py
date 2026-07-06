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


if __name__ == '__main__':
    
    # Connect the robot
    ep_robot = connect()

    # Chassis module
    ep_chassis = ep_robot.chassis

    # Values
    x_val = 0.5  # Speed (m/s)
    y_val = 0.3  # Speed (m/s)
    z_val = 30   # Rotation speed (º/s)
    timeout = 5  # Max time allowed to move(s)

    # Move 3 seconds on x-axis
    ep_chassis.drive_speed(x=x_val, y=0, z=0, timeout=timeout)
    time.sleep(3)

    # Return to initial position within 3s
    ep_chassis.drive_speed(x=-x_val, y=0, z=0, timeout=timeout)
    time.sleep(3)

    # Move 3 seconds on y-axis
    ep_chassis.drive_speed(x=0, y=-y_val, z=0, timeout=timeout)
    time.sleep(3)

    # Return to initial position within 3s
    ep_chassis.drive_speed(x=0, y=y_val, z=0, timeout=timeout)
    time.sleep(3)

    # Rotate left during 3 seconds
    ep_chassis.drive_speed(x=0, y=0, z=-z_val, timeout=timeout)
    time.sleep(3)

    # Rotate right during 3 seconds
    ep_chassis.drive_speed(x=0, y=0, z=z_val, timeout=timeout)
    time.sleep(3)

    # Stop (optional)
    ep_chassis.drive_speed(x=0, y=0, z=0, timeout=timeout)

    # End connection
    ep_robot.close()

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

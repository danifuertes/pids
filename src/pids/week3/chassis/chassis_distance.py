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
    x_val = 1.0     # x-axis moves the robot forward/backward (meters)
    y_val = 1.0     # y-axis moves the robot to the right/left (meters)
    z_val = 90      # z-axis rotates the robot (degrees)
    speed_xy = 1.0  # m/s
    speed_z = 45    # º/s

    # Move 0.5 meters in x-axis at a speed of 0.5 m/s
    ep_chassis.move(x=x_val, y=0, z=0, xy_speed=speed_xy).wait_for_completed()
    time.sleep(1)

    # Return to initial position at a speed of 0.5 m/s
    ep_chassis.move(x=-x_val, y=0, z=0, xy_speed=speed_xy).wait_for_completed()
    time.sleep(1)

    # Move 0.6 meters in y-axis at a speed of 0.5 m/s
    ep_chassis.move(x=0, y=-y_val, z=0, xy_speed=speed_xy).wait_for_completed()
    time.sleep(1)

    # Return to initial position at a speed of 0.5 m/s
    ep_chassis.move(x=0, y=y_val, z=0, xy_speed=speed_xy).wait_for_completed()
    time.sleep(1)

    # Rotate 90º to the left at a speed of 45º/s
    ep_chassis.move(x=0, y=0, z=z_val, z_speed=speed_z).wait_for_completed()
    time.sleep(1)

    # Rotate 90º to the right at a speed of 45º/s
    ep_chassis.move(x=0, y=0, z=-z_val, z_speed=speed_z).wait_for_completed()
    time.sleep(1)

    # End connection
    ep_robot.close()

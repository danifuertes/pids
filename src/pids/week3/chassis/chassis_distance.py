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
    x_val = 1.0     # x-axis moves the robot forward/backward (meters)
    y_val = 1.0     # y-axis moves the robot to the right/left (meters)
    z_val = 90      # z-axis rotates the robot (degrees)
    speed_xy = 1.0  # m/s
    speed_z = 45    # º/s

    # Move forward x_val meters, then back to the start (at speed_xy m/s)
    ep_chassis.move(x=x_val, y=0, z=0, xy_speed=speed_xy).wait_for_completed()
    time.sleep(1)
    ep_chassis.move(x=-x_val, y=0, z=0, xy_speed=speed_xy).wait_for_completed()
    time.sleep(1)

    # Move left y_val meters, then back to the start
    ep_chassis.move(x=0, y=-y_val, z=0, xy_speed=speed_xy).wait_for_completed()
    time.sleep(1)
    ep_chassis.move(x=0, y=y_val, z=0, xy_speed=speed_xy).wait_for_completed()
    time.sleep(1)

    # Rotate z_val degrees left, then back to the start (at speed_z º/s)
    ep_chassis.move(x=0, y=0, z=z_val, z_speed=speed_z).wait_for_completed()
    time.sleep(1)
    ep_chassis.move(x=0, y=0, z=-z_val, z_speed=speed_z).wait_for_completed()
    time.sleep(1)

    # End connection
    ep_robot.close()

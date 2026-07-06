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

    # Gimbal module
    ep_gimbal = ep_robot.gimbal

    # Move gimbal to initial position: pitch=0, yaw=0
    ep_gimbal.moveto(pitch=0, yaw=0, pitch_speed=100, yaw_speed=100).wait_for_completed()

    # Move the gimbal to the right during 3 seconds at a speed of 30º/s
    slp = 3
    ep_gimbal.drive_speed(pitch_speed=0, yaw_speed=30)
    time.sleep(slp)

    # Move the gimbal to the left during 3 seconds at a speed of 30º/s
    ep_gimbal.drive_speed(pitch_speed=0, yaw_speed=-30)
    time.sleep(slp)

    # Move up the gimbal during 3 seconds at a speed of 10º/s
    ep_gimbal.drive_speed(pitch_speed=10, yaw_speed=0)
    time.sleep(slp)

    # Move down the gimbal during 3 seconds at a speed of 10º/s
    ep_gimbal.drive_speed(pitch_speed=-10, yaw_speed=0)
    time.sleep(slp)

    # Move gimbal to initial position: pitch=0, yaw=0
    ep_gimbal.moveto(pitch=0, yaw=0, pitch_speed=100, yaw_speed=100).wait_for_completed()

    # End connection
    ep_robot.close()

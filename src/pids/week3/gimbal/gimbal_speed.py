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

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

    # Values
    pitch_val = 15  # Pitch: Move the gimbal up/down (º)
    yaw_val = 30    # Yaw: Move the gimbal right/left (º)

    # Move gimbal to initial position: pitch=0, yaw=0
    ep_gimbal.moveto(pitch=0, yaw=0).wait_for_completed()

    # Move the gimbal up and right to the position (15º, 90º) with the specified speeds
    ep_gimbal.moveto(pitch=15, yaw=90, pitch_speed=50, yaw_speed=100).wait_for_completed()

    # Move the gimbal left and down to the position (-15º, -90º) with the specified speeds
    ep_gimbal.moveto(pitch=-15, yaw=-90, pitch_speed=100, yaw_speed=30).wait_for_completed()

    # Move gimbal to initial position: pitch=0, yaw=0
    ep_gimbal.moveto(pitch=0, yaw=0).wait_for_completed()

    # Move the gimbal 30º to the right 3 consecutive times
    ep_gimbal.move(pitch=0, yaw=yaw_val).wait_for_completed()
    ep_gimbal.move(pitch=0, yaw=yaw_val).wait_for_completed()
    ep_gimbal.move(pitch=0, yaw=yaw_val).wait_for_completed()

    # Move the gimbal 30º to the right 3 consecutive times
    ep_gimbal.move(pitch=0, yaw=-yaw_val).wait_for_completed()
    ep_gimbal.move(pitch=0, yaw=-yaw_val).wait_for_completed()
    ep_gimbal.move(pitch=0, yaw=-yaw_val).wait_for_completed()

    # Move up the gimbal 15º
    ep_gimbal.move(pitch=pitch_val, yaw=0).wait_for_completed()

    # Move down the gimbal 15º
    ep_gimbal.move(pitch=-pitch_val, yaw=0).wait_for_completed()

    # Move gimbal to initial position: pitch=0, yaw=0
    ep_gimbal.moveto(pitch=0, yaw=0).wait_for_completed()

    # End connection
    ep_robot.close()

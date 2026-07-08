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

    # Move the gimbal right yaw_valº three times in a row
    ep_gimbal.move(pitch=0, yaw=yaw_val).wait_for_completed()
    ep_gimbal.move(pitch=0, yaw=yaw_val).wait_for_completed()
    ep_gimbal.move(pitch=0, yaw=yaw_val).wait_for_completed()

    # Move the gimbal left yaw_valº three times in a row
    ep_gimbal.move(pitch=0, yaw=-yaw_val).wait_for_completed()
    ep_gimbal.move(pitch=0, yaw=-yaw_val).wait_for_completed()
    ep_gimbal.move(pitch=0, yaw=-yaw_val).wait_for_completed()

    # Tilt the gimbal up pitch_valº
    ep_gimbal.move(pitch=pitch_val, yaw=0).wait_for_completed()

    # Tilt the gimbal down pitch_valº
    ep_gimbal.move(pitch=-pitch_val, yaw=0).wait_for_completed()

    # Move gimbal to initial position: pitch=0, yaw=0
    ep_gimbal.moveto(pitch=0, yaw=0).wait_for_completed()

    # End connection
    ep_robot.close()

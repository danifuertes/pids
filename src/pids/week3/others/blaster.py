import time
from robomaster import robot, blaster


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

    # Blaster module
    ep_blaster = ep_robot.blaster

    # Fire 1 water ball
    ep_blaster.fire(times=1)
    time.sleep(2)

    # Fire 3 water balls
    ep_blaster.fire(fire_type=blaster.WATER_FIRE, times=3)
    time.sleep(2)

    # Fire 1 infrared laser shot
    ep_blaster.fire(fire_type=blaster.INFRARED_FIRE)
    time.sleep(2)

    # Fire 3 infrared laser shots
    ep_blaster.fire(fire_type=blaster.INFRARED_FIRE, times=3)
    time.sleep(2)

    # End connection
    ep_robot.close()

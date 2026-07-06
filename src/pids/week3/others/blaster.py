import time
from robomaster import robot, blaster


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

    # Blaster module
    ep_blaster = ep_robot.blaster

    # Shot 1 ball
    ep_blaster.fire(times=1)
    time.sleep(2)

    # Shot 3 balls
    ep_blaster.fire(fire_type=blaster.WATER_FIRE, times=3)
    time.sleep(2)

    # Shot 1 infrared laser
    ep_blaster.fire(fire_type=blaster.INFRARED_FIRE)
    time.sleep(2)

    # Shot 3 infrared laser
    ep_blaster.fire(fire_type=blaster.INFRARED_FIRE, times=3)
    time.sleep(2)

    # End connection
    ep_robot.close()

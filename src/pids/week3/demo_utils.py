import cv2
import numpy as np
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


def auto_aim(image, best_pred) -> float:
    """
    Once a robot is found, get the angle to move the gimbal to that robot.
    :param image: image containing bounding box.
    :param best_pred: best box prediction.
    :return:
        alpha: angle between image center and best bounding found.
    """

    # Get image shape
    h, w = image.shape[:2]

    # Get camera center
    cam_center = np.array([w / 2, h / 2])

    # Get (best) bounding box center
    box_center = np.array([(best_pred[2] + best_pred[0]) / 2, (best_pred[3] + best_pred[1]) / 2])

    # Get distance between camera center and box center
    box_cam_dist = box_center[0] - cam_center[0]

    # Check if it's on the right or on the left of the image
    right_left = np.sign(box_cam_dist)

    # Get distance to robot. Camera has 120º of field of view (FOV), half of that is 60º <==> 2 * pi / 3
    rob_cam_dist = w / (2 * np.tan(np.pi / 3))

    # Calculate angle
    box_cam_dist = np.abs(box_cam_dist)
    alpha = right_left * np.rad2deg(np.arctan(box_cam_dist / rob_cam_dist)) * 90 / 120  # Seems FOV != 120º -> FOV = 90º
    return alpha


def detect_and_shoot(ep_robot, model):
    
    # Camera module
    ep_camera = ep_robot.camera

    # Start video stream
    ep_camera.start_video_stream(display=False)

    # Receive image
    image = ep_camera.read_cv2_image()

    # Stop video stream
    ep_camera.stop_video_stream()

    # Make predictions
    ...

    # Move gimbal to best bounding box
    ...

    # Shoot
    ...

    # Save image with predictions
    ...

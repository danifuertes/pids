import cv2
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

    # Camera module
    ep_camera = ep_robot.camera

    # Create OpenCV Video Writer
    out = cv2.VideoWriter('recording.mp4', cv2.VideoWriter_fourcc(*'mp4v'), 30, (1280, 720))

    # Start video stream
    ep_camera.start_video_stream(display=False)

    # Record and transmit 200 frames
    for i in range(0, 200):

        # Receive image
        img = ep_camera.read_cv2_image()

        # Show image
        cv2.imshow('Robot', img)

        # Save image
        out.write(img)
        cv2.waitKey(1)

    # End video
    cv2.destroyAllWindows()
    out.release()
    ep_camera.stop_video_stream()

    # End connection
    ep_robot.close()

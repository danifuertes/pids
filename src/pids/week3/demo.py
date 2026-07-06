from pids.week3.demo_utils import *


if __name__ == '__main__':
    
    # Connect the robot
    ep_robot = connect()

    # Load your model
    model = ...

    # Move the robot - Target 1
    ...

    # Move the gimbal - Target 1
    ...

    # Detect and shoot - Target 1
    detect_and_shoot(ep_robot, model)

    # Repeat for other targets
    ...

    # End connection
    ep_robot.close()

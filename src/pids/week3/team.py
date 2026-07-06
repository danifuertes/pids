"""
This script can only be executed through router connection (networking mode)
"""


from multi_robomaster import multi_robot
from robomaster import blaster


def group_task(robot_group):
    x = 0.3
    y = 0.3
    z = 90

    # Move backward 0.3 meters
    robot_group.chassis.move(-x, 0, 0, 2, 180).wait_for_completed()

    # Move forward 0.3 meters
    robot_group.chassis.move(x, 0, 0, 2, 180).wait_for_completed()

    # Move left 0.3 meters
    robot_group.chassis.move(0, -y, 0, 2, 180).wait_for_completed()

    # Move right 0.3 meters
    robot_group.chassis.move(0, y, 0, 2, 180).wait_for_completed()

    # Rotate 90º to the left
    robot_group.chassis.move(0, 0, z, 2, 180).wait_for_completed()

    # Rotate 90º to the right
    robot_group.chassis.move(0, 0, -z, 2, 180).wait_for_completed()


def task_with_params(num_shoots):
    def task(robot_group):
        robot_group.blaster.fire(fire_type=blaster.INFRARED_FIRE, times=num_shoots)
    return task


if __name__ == '__main__':

    # Indicate which robots will be used. Options are: teseo, perseo, heracles, eneas, jason, aquiles
    robot_list = ['teseo', 'perseo']

    # Serial Numbers of available robots
    sn_dict = {
        'teseo': '3JKCK160030359',
        'perseo': '3JKCK1600303HQ',
        'heracles': '3JKCK16003042N',
        'eneas': '3JKCK16003039B',
        'jason': '3JKCK7W0030DKB',
        'aquiles': '159CK9200607QK',
    }
    sn_list = [sn_dict[r] for r in robot_list]

    # Initialize multi-robot class
    multi_robots = multi_robot.MultiEP()
    multi_robots.initialize()

    # Find robots
    number = multi_robots.number_id_by_sn(*[[i, r] for i, r in enumerate(sn_list)])
    print("The number of robots is: {0}".format(number))

    # ONE GROUP: A group containing all the robots will perform the same task simultaneously
    group = multi_robots.build_group(range(len(sn_list)))  # The group is composed by robots: [0, 1, 2, ...]
    multi_robots.run([group, group_task])                  # Run group

    # MULTIPLE GROUPS: Each group, composed by one robot each, will perform different tasks simultaneously
    groups = [multi_robots.build_group([i]) for i in range(len(sn_list))]  # List of groups: [[0], [1], [2]...]
    multi_robots.run(*[[group, task_with_params(i+1)] for i, group in enumerate(groups)])  # Run list of groups
    # |--> Simplified code: multi_robots.run([groups[0], task_with_params(1)], [groups[1], task_with_params(2)], ...)

    # ******************************************************************************************************************
    # *** Note that you can make combinations of groups like: [[0, 1], [2]], which means that robots 0 and 1 perform ***
    # *** the same task and robot 2 perform another different task).                                                 ***
    # ******************************************************************************************************************

    # End execution
    print("Game over")
    multi_robots.close()

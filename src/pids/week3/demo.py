from pids.week3.demo_utils import *


if __name__ == '__main__':

    # ------------------------------------------------------------------
    # Settings: make these match the model you trained in week 2
    # ------------------------------------------------------------------
    model_name = 'faster_rcnn_v1'                          # Same model you trained
    model_path = f'../models/{model_name}/model_best.pt'   # Best checkpoint from train.ipynb
    num_classes = 2                                        # 0 = background, 1 = robot
    use_gpu = True                                         # Use the GPU if one is available

    # Connect the robot
    ep_robot = connect()

    # Load your trained model (same loader as week 2; no optimizer needed for inference)
    model, _, _, device = get_model(
        model_name=model_name,
        model_path=model_path,
        num_classes=num_classes,
        lr_data=None,
        pretrained=False,
        use_gpu=use_gpu,
    )

    # ================= Build your demo below ==========================

    # Move the robot into position - Target 1
    #   See chassis/chassis_distance.py or chassis/chassis_speed.py
    ...

    # Point the gimbal roughly towards the target - Target 1
    #   See gimbal/gimbal_degrees.py or gimbal/gimbal_speed.py
    ...

    # Detect the target and shoot it - Target 1
    detect_and_shoot(ep_robot, model)

    # Repeat for the other targets
    ...
    # ==================================================================

    # End connection
    ep_robot.close()

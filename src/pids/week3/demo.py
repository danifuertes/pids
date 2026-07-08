from pids.week3.demo_utils import *


def detect_and_shoot(ep_robot, model, score_threshold=0.5, resize_shape=None):
    """Capture an image, detect the enemy robot, aim the gimbal at it and shoot.

    The capture and inference are done for you by predict() (STEP 1). Your job
    is to use the predictions to aim and fire (STEPS 2-4).
    :param ep_robot: connected RoboMaster object (see connect()).
    :param model: trained detection model (see get_model()).
    :param score_threshold: minimum confidence to accept a detection.
    :param resize_shape: (height, width) to resize the image for the model, or None.
    :return: (image, prediction) — the RGB image and a dict of NumPy arrays with
             keys 'boxes' (N, 4 as [x_min, y_min, x_max, y_max]), 'scores' (N,) and 'labels' (N,).
    """

    # --- STEP 1: capture the frame and run the detector (done for you) --------
    image, prediction = predict(ep_robot, model, resize_shape=resize_shape)

    # --- STEP 2: choose the best detection (YOUR CODE) ------------------------
    # Guides:
    #   * Keep only the boxes whose score is >= score_threshold
    #   * If there is nothing to shoot, `return image, prediction`
    #     so the picture is still saved afterwards
    #   * Otherwise pick the box with the HIGHEST score
    best_box = ...

    # --- STEP 3: aim the gimbal at the target (YOUR CODE) ---------------------
    # Guides:
    #   * auto_aim(image, best_box) returns the yaw angle (degrees) to the target
    #   * Rotate the gimbal by that angle
    ...

    # --- STEP 4: shoot (YOUR CODE) --------------------------------------------
    # Guides:
    #   * Fire the blaster using blaster.INFRARED_FIRE
    ...

    return image, prediction


if __name__ == '__main__':

    # Parameters
    model_name = 'faster_rcnn_v1'                          # Same model you trained
    model_path = f'../models/{model_name}/model_best.pt'   # Best checkpoint from train.ipynb
    num_classes = 2                                        # 0 = background, 1 = robot
    use_gpu = True                                         # Use the GPU if one is available
    resize_shape = None                                    # (height, width) to resize the camera image, or None
    score_threshold = 0.5                                  # Minimum confidence to accept/draw a detection

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

    # ================= Target 1 ==========================

    # Move the robot
    ...

    # Point the gimbal towards the target
    ...

    # Detect the target, aim and shoot
    image, prediction = detect_and_shoot(ep_robot, model, score_threshold=score_threshold, resize_shape=resize_shape)

    # Save a picture of what the robot detected
    plot_predictions(image, prediction, target_id=1, score_threshold=score_threshold)
    # ==================================================================
    
    # Repeat for the other targets
    ...

    # End connection
    ep_robot.close()

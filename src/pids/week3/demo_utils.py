import os
import random

import cv2
import numpy as np
import torch
from robomaster import robot, blaster
from torchvision.models import detection
import torchvision.transforms.v2 as transforms
from typing import Tuple, Union, Any


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


def new_history() -> dict:
    """Empty training history: losses per epoch, best validation loss and last finished epoch."""
    return {'train_loss': [], 'valid_loss': [], 'lr': [], 'best_value': np.inf, 'current_epoch': 0}


def torch_load_cpu(path: str) -> Any:
    """Load a checkpoint onto the CPU (works even if it was saved on a GPU)."""
    return torch.load(path, map_location='cpu')


def load_checkpoint(path: str, model: Any, device: torch.device, optimizer: torch.optim = None) -> Tuple[Any, Any, dict]:
    """Load model weights, optimizer and RNG state from a checkpoint (to resume training or to test)."""
    checkpoint = torch_load_cpu(path)

    # Model weights
    model.load_state_dict({**model.state_dict(), **checkpoint.get('model', {})})

    # Random-number-generator state (single device: no multi-GPU here)
    if 'rng_state' in checkpoint:
        torch.set_rng_state(checkpoint['rng_state'])
    if torch.cuda.is_available() and checkpoint.get('cuda_rng_state') is not None:
        torch.cuda.set_rng_state(checkpoint['cuda_rng_state'])
    if 'numpy_rng_state' in checkpoint:
        np.random.set_state(checkpoint['numpy_rng_state'])
    if 'python_rng_state' in checkpoint:
        random.setstate(checkpoint['python_rng_state'])

    # Optimizer state (only needed to resume training)
    if optimizer is not None and 'optimizer' in checkpoint:
        optimizer.load_state_dict(checkpoint['optimizer'])
        for state in optimizer.state.values():
            for k, v in state.items():
                if torch.is_tensor(v):
                    state[k] = v.to(device)

    history = checkpoint.get('history', new_history())
    return model, optimizer, history


def torchvision_model(model_name: str, pretrained: bool = False, num_classes: int = 2) -> Any:
    """Build a torchvision detection model and adapt its head to `num_classes` (0=background, 1=object)."""
    model_dict = {
        'faster_rcnn_v1': detection.fasterrcnn_resnet50_fpn,
        'faster_rcnn_v2': detection.fasterrcnn_resnet50_fpn_v2,
        'faster_rcnn_v3': detection.fasterrcnn_mobilenet_v3_large_fpn,
        'retinanet_v1': detection.retinanet_resnet50_fpn,
        'retinanet_v2': detection.retinanet_resnet50_fpn_v2,
        'ssd_v1': detection.ssd300_vgg16,
        'ssd_v2': detection.ssdlite320_mobilenet_v3_large,
    }
    assert model_name in model_dict, f"Unknown model '{model_name}'. Choose one of: {list(model_dict)}"

    # Load the architecture (optionally with COCO pre-trained weights)
    model = model_dict[model_name](weights='COCO_V1' if pretrained else None)

    # Replace the classification head so it predicts OUR number of classes
    if 'faster_rcnn' in model_name:
        in_features = model.roi_heads.box_predictor.cls_score.in_features
        model.roi_heads.box_predictor = detection.faster_rcnn.FastRCNNPredictor(in_features, num_classes)
    elif 'retinanet' in model_name:
        in_features = model.head.classification_head.cls_logits.in_channels
        num_anchors = model.head.classification_head.num_anchors
        model.head.classification_head = detection.retinanet.RetinaNetClassificationHead(in_features, num_anchors, num_classes)
    elif model_name == 'ssd_v1':
        in_features = [module.in_channels for module in model.head.classification_head.module_list]
        num_anchors = model.anchor_generator.num_anchors_per_location()
        model.head.classification_head = detection.ssd.SSDClassificationHead(in_features, num_anchors, num_classes)
    elif model_name == 'ssd_v2':
        in_features = [module[0][0].in_channels for module in model.head.classification_head.module_list]
        num_anchors = model.anchor_generator.num_anchors_per_location()
        model.head.classification_head = detection.ssd.SSDClassificationHead(in_features, num_anchors, num_classes)
    return model


def get_model(model_name: str, model_path: str = '', num_classes: int = 2, lr_data: list = None,
              pretrained: bool = False, use_gpu: bool = False) -> Tuple[Any, Any, dict, torch.device]:
    """Create the model (and optimizer) and, if a checkpoint exists at `model_path`, resume from it."""
    device = torch.device('cuda' if use_gpu and torch.cuda.is_available() else 'cpu')
    model = torchvision_model(model_name, pretrained, num_classes).to(device)

    # Optimizer (only when training, i.e. when learning-rate settings are given)
    if lr_data:
        params = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.SGD(params, lr=lr_data[0], momentum=lr_data[1], weight_decay=lr_data[2])
    else:
        optimizer = None

    # Resume from a checkpoint if one is found
    if os.path.isfile(model_path):
        model, optimizer, history = load_checkpoint(model_path, model, device, optimizer)
        print(f"Resumed from '{model_path}' (epoch {history['current_epoch']}).")
    else:
        history = new_history()
        print(f"No checkpoint at '{model_path}'. Starting from scratch.")
    return model, optimizer, history, device


def get_transform(resize_shape: Union[tuple, None] = None) -> transforms.Compose:
    """Turn an image into a float tensor in [0, 1]. Detection models normalise internally, so we do NOT normalise here."""
    t = [transforms.ToTensor()]
    if resize_shape:
        t.append(transforms.Resize(resize_shape, antialias=True))
    return transforms.Compose(t)


def auto_aim(image, box) -> float:
    """Yaw angle (degrees) from the image centre to the centre of a detected box.

    Rotating the gimbal by this angle brings the target to the middle of the view.
    :param image: image the box was detected on, shape (height, width, 3).
    :param box: detected box as [x_min, y_min, x_max, y_max].
    :return: alpha, yaw angle in degrees (negative = left, positive = right).
    """
    height, width = image.shape[:2]

    # Horizontal offset (pixels) between the box centre and the image centre
    box_center_x = (box[0] + box[2]) / 2
    offset = box_center_x - width / 2

    # Turn that pixel offset into an angle using the camera geometry. arctan is
    # an odd function, so the sign of `offset` already tells left from right.
    focal = width / (2 * np.tan(np.pi / 3))                 # ~120º field-of-view lens
    alpha = np.rad2deg(np.arctan(offset / focal)) * 90 / 120  # measured FOV is closer to 90º
    return alpha


def detect_and_shoot(ep_robot, model, score_threshold=0.5):
    """Capture an image, detect the enemy robot, aim the gimbal at it and shoot.

    The camera capture is already done for you. Fill in the detection, aiming
    and shooting steps using what you learned in week 2 (model inference) and
    in the scripts of this week (gimbal and blaster).
    :param ep_robot: connected RoboMaster object (see connect()).
    :param model: trained detection model (see get_model()).
    :param score_threshold: minimum confidence to accept a detection.
    """

    # --- Capture one image from the robot camera (done for you) ---------------
    ep_camera = ep_robot.camera
    ep_camera.start_video_stream(display=False)
    image = ep_camera.read_cv2_image()          # BGR image, shape (height, width, 3)
    ep_camera.stop_video_stream()

    # --- STEP 1: run the model on the image -----------------------------------
    # Guides:
    #   * OpenCV returns BGR, but the model was trained on RGB, so convert it:
    #         rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    #   * Pre-process it exactly like in week 2 (get_transform is imported here):
    #         transform = get_transform()
    #         tensor = transform(rgb)
    #   * Run inference in evaluation mode, without gradients, on the model's device:
    #         device = next(model.parameters()).device
    #         model.eval()
    #         with torch.no_grad():
    #             prediction = model([tensor.to(device)])[0]
    #   * `prediction` is a dict with 'boxes', 'scores' and 'labels' (see test.ipynb).
    prediction = ...

    # --- STEP 2: choose the best detection ------------------------------------
    # Guides:
    #   * Move the boxes and scores to CPU/numpy so they are easy to work with.
    #   * Keep only the boxes whose score is >= score_threshold.
    #   * If none survive there is nothing to shoot: print a message and `return`.
    #   * Otherwise pick the box with the HIGHEST score (the clearest robot).
    #   * A box is [x_min, y_min, x_max, y_max].
    best_box = ...

    # --- STEP 3: aim the gimbal at the target ---------------------------------
    ...

    # --- STEP 4: shoot --------------------------------------------------------
    ...

    # --- STEP 5: save the image with the detection (to check your work) -------
    ...

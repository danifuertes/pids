import os
import random

import cv2
import numpy as np
import torch
from robomaster import robot, blaster
from torchvision.models import detection
import torchvision.transforms.v2 as transforms
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
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


def resize_boxes(boxes: Any, resize_shape: tuple, image_shape: tuple) -> Any:
    """Rescale [x_min, y_min, x_max, y_max] boxes when the image is resized (height, width)."""
    scale_h, scale_w = resize_shape[0] / image_shape[0], resize_shape[1] / image_shape[1]
    boxes[:, [0, 2]] *= scale_w
    boxes[:, [1, 3]] *= scale_h
    return boxes


def predict(ep_robot, model, resize_shape=None):
    """Capture one camera frame, run the detector on it and return the results.

    Handles the whole inference pipeline: frame capture, BGR->RGB, pre-processing
    (get_transform), model inference and post-processing (predictions moved to
    CPU/NumPy and boxes scaled back to the original image size).
    :param ep_robot: connected RoboMaster object (see connect()).
    :param model: trained detection model (see get_model()).
    :param resize_shape: (height, width) to resize the image for the model, or None.
    :return: (image, prediction) — the original-size RGB image and a dict of NumPy
             arrays 'boxes' (N, 4 as [x_min, y_min, x_max, y_max]), 'scores' (N,), 'labels' (N,).
    """
    # Grab one frame from the robot camera
    ep_camera = ep_robot.camera
    ep_camera.start_video_stream(display=False)
    image = ep_camera.read_cv2_image()              # BGR image, shape (height, width, 3)
    ep_camera.stop_video_stream()
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # RGB image, shape (height, width, 3)

    # Make predictions
    device = next(model.parameters()).device
    transform = get_transform(resize_shape)
    model.eval()
    with torch.no_grad():
        output = model([transform(image).to(device)])[0]

    # Bring the predictions to CPU/NumPy so they are easy to work with
    prediction = {key: value.detach().cpu().numpy() for key, value in output.items()}

    # Scale predictions back to the original image size if resize was applied
    if resize_shape is not None:
        prediction['boxes'] = resize_boxes(prediction['boxes'], image.shape[:2], resize_shape)

    return image, prediction


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


def plot_predictions(image, prediction, target_id, score_threshold=0.5, path='predictions'):
    """Draw the predicted boxes (above score_threshold) on the image and save it.

    Same plotting style as week2's test.ipynb, but it saves one figure per
    target (file name = target id) instead of showing it, since the demo runs
    as a script and not in a notebook.
    :param image: RGB image the predictions were computed on.
    :param prediction: dict with NumPy arrays 'boxes' (N, 4) and 'scores' (N,).
    :param target_id: identifier of the target; used as the output file name.
    :param score_threshold: minimum confidence to draw a box.
    :param path: folder where the figures are saved (created if it does not exist).
    """
    boxes = prediction['boxes']
    scores = prediction['scores']

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.imshow(image)
    ax.axis('off')
    ax.set_title(f'Target {target_id}')
    for (x_min, y_min, x_max, y_max), score in zip(boxes, scores):
        if score < score_threshold:
            continue
        ax.add_patch(Rectangle((x_min, y_min), x_max - x_min, y_max - y_min,
                               linewidth=2, edgecolor='lime', facecolor='none'))
        ax.text(x_min, y_min - 5, f'{score:.2f}', color='white', fontsize=10,
                bbox=dict(facecolor='black', alpha=0.6, pad=1))
    os.makedirs(path, exist_ok=True)
    fig.savefig(os.path.join(path, f'{target_id}.png'), bbox_inches='tight')
    plt.close(fig)

import sys
import math
import time
import threading
import numpy as np
import torch
from robomaster import robot, led

from pids.nav.spline_utils import BSpline


# Sign conventions at the SDK boundary (VERIFY ON THE ROBOT with sign_test()).
# Internally: x forward, y left, yaw counter-clockwise positive, radians.
Y_SIGN_CMD = -1         # drive_speed: y > 0 is right
YAW_SIGN_CMD = -1       # drive_speed: z > 0 is clockwise
Y_SIGN_FEEDBACK = -1    # sub_position: y > 0 is right
YAW_SIGN_FEEDBACK = -1  # sub_attitude: yaw > 0 is clockwise
TOF_INDEX = 0           # Index of the frontal ToF in the sub_distance list

# Control parameters
RATE = 10           # Control loop frequency (Hz)
V_MIN = 0.05        # Minimum forward speed so the robot never stalls on the path (m/s)
K_P = 1.5           # Position error gain (1/s)
K_THETA = 2.0       # Heading error gain (1/s)
W_MAX = math.radians(60)  # Max yaw rate (rad/s)
POS_TOL = 0.04      # Final position tolerance (m)
YAW_TOL = math.radians(2)  # In-place rotation tolerance (rad)
MIN_DIST = 0.3      # Stop if the ToF reads less than this (m)


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


def wrap(angle):
    """Wrap an angle to [-pi, pi).

    :param angle: angle in radians.
    :return: wrapped angle in radians.
    """
    return (angle + math.pi) % (2 * math.pi) - math.pi


def commands_to_waypoints(commands):
    """Dead-reckon a list of commands from the pose (0, 0, 0).

    Vocabulary: ('forward', metres), ('left', degrees), ('right', degrees).
    Turns between two forward legs become rounded corners of the path.
    :param commands: list of (name, value) tuples.
    :return: waypoints (N x 2 array), heading of the first leg and final heading (rad).
    """
    pos = np.zeros(2)
    heading = 0.0
    first_heading = None
    waypoints = [pos.copy()]
    for name, value in commands:
        if name == 'forward':
            if value <= 0:
                raise ValueError("'forward' needs a positive distance, got {}".format(value))
            if first_heading is None:
                first_heading = heading
            pos = pos + value * np.array([math.cos(heading), math.sin(heading)])
            waypoints.append(pos.copy())
        elif name == 'left':
            heading = wrap(heading + math.radians(value))
        elif name == 'right':
            heading = wrap(heading - math.radians(value))
        else:
            raise ValueError("Unknown command '{}'. Use 'forward', 'left' or 'right'".format(name))
    return np.array(waypoints), first_heading, heading


def waypoints_to_spline(waypoints, n_samples=80):
    """Fit one cubic B-spline (8 control points) per waypoint pair and sample it.

    :param waypoints: N x 2 array of points (m), N >= 2.
    :param n_samples: samples per segment.
    :return: dict with arrays s (arc length), x, y, theta (rad), kappa (1/m).
    """
    W = torch.tensor(waypoints, dtype=torch.float64)
    n_seg = len(W) - 1

    # Boundary tangents: leave W_i along leg i, arrive at W_{i+1} along leg i+1
    legs = W[1:] - W[:-1]
    v0 = legs
    v1 = torch.cat([legs[1:], legs[-1:]])

    # Fixed control points (knots [0,0,0,0,.2,.4,.6,.8,1,1,1,1], zero start acceleration)
    P = torch.zeros(n_seg, 8, 2, dtype=torch.float64)
    P[:, 0] = W[:-1]
    P[:, 1] = P[:, 0] + 0.2 * v0 / 3
    P[:, 2] = P[:, 1] + 2 * (P[:, 1] - P[:, 0])
    P[:, 7] = W[1:]
    P[:, 6] = P[:, 7] - 0.2 * v1 / 3

    # Free control points P3..P5 minimise the bending energy of the control polygon
    A = torch.tensor([[6., -4., 1.], [-4., 6., -4.], [1., -4., 6.]], dtype=torch.float64)
    B = torch.stack([
        -(P[:, 1] - 4 * P[:, 2]),
        -(P[:, 2] + P[:, 6]),
        -(-4 * P[:, 6] + P[:, 7]),
    ], dim=1)
    P[:, 3:6] = torch.linalg.solve(A, B)

    # Sample positions and derivatives of every segment
    bspline = BSpline.uniform((0, 1), n_segments=5, degree=3, dtype=torch.float64)
    t = torch.linspace(0, 1, n_samples, dtype=torch.float64)
    B0, B1, B2 = bspline(t), bspline.derivative(t, 1), bspline.derivative(t, 2)
    C, dC, ddC = B0 @ P, B1 @ P, B2 @ P  # (n_seg, n_samples, 2)

    # Concatenate segments without duplicating the joints
    C = torch.cat([C[0]] + [c[1:] for c in C[1:]]).numpy()
    dC = torch.cat([dC[0]] + [c[1:] for c in dC[1:]]).numpy()
    ddC = torch.cat([ddC[0]] + [c[1:] for c in ddC[1:]]).numpy()

    # Arc length, heading and signed curvature
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))])
    theta = np.arctan2(dC[:, 1], dC[:, 0])
    kappa = (dC[:, 0] * ddC[:, 1] - dC[:, 1] * ddC[:, 0]) / np.linalg.norm(dC, axis=1) ** 3
    return {'s': s, 'x': C[:, 0], 'y': C[:, 1], 'theta': theta, 'kappa': kappa}


def speed_profile(path, v_max=0.4, a_max=0.5, a_lat_max=0.5):
    """Speed along the path, limited by curvature and acceleration, from rest to rest.

    :param path: dict from waypoints_to_spline().
    :param v_max: max speed (m/s), keep it <= 0.5.
    :param a_max: max tangential acceleration (m/s^2).
    :param a_lat_max: max lateral acceleration (m/s^2).
    :return: array v (m/s), one value per path sample.
    """
    ds = np.diff(path['s'])
    v = np.minimum(v_max, np.sqrt(a_lat_max / np.maximum(np.abs(path['kappa']), 1e-6)))
    v[0] = v[-1] = 0

    # Forward pass (acceleration) and backward pass (deceleration)
    for i in range(1, len(v)):
        v[i] = min(v[i], math.sqrt(v[i - 1] ** 2 + 2 * a_max * ds[i - 1]))
    for i in range(len(v) - 2, -1, -1):
        v[i] = min(v[i], math.sqrt(v[i + 1] ** 2 + 2 * a_max * ds[i]))
    return v


def plan(commands, v_max=0.4):
    """Turn commands into steps: optional in-place rotations and one smooth path.

    :param commands: list of (name, value) tuples, see commands_to_waypoints().
    :param v_max: max speed (m/s).
    :return: list of ('rotate', target_heading) or ('path', path_dict) steps.
    """
    waypoints, first_heading, final_heading = commands_to_waypoints(commands)
    steps = []

    # No translation at all: just rotate
    if len(waypoints) < 2:
        if final_heading != 0:
            steps.append(('rotate', final_heading))
        return steps

    # Face the first leg, follow the path, then face the final heading
    if abs(first_heading) > YAW_TOL:
        steps.append(('rotate', first_heading))
    path = waypoints_to_spline(waypoints)
    path['v'] = speed_profile(path, v_max=v_max)
    steps.append(('path', path))
    if abs(wrap(final_heading - path['theta'][-1])) > YAW_TOL:
        steps.append(('rotate', final_heading))
    return steps


def track_step(path, pose, idx, v_max):
    """One iteration of the path tracker (pure function, no robot).

    :param path: dict with s, x, y, theta, kappa, v.
    :param pose: (x, y, theta) of the robot in the path frame.
    :param idx: closest path index found in the previous iteration.
    :param v_max: max speed (m/s).
    :return: body-frame command (vx, vy, wz) in m/s and rad/s, new idx, done flag.
    """
    x, y, th = pose
    p = np.array([x, y])
    pts = np.stack([path['x'], path['y']], axis=1)

    # Closest point, searching only forward (up to 0.5 m ahead)
    end = np.searchsorted(path['s'], path['s'][idx] + 0.5) + 1
    idx = idx + int(np.argmin(np.linalg.norm(pts[idx:end] - p, axis=1)))
    last = len(path['s']) - 1

    # Done when close to the end and at the end of the path
    if np.linalg.norm(pts[-1] - p) < POS_TOL and path['s'][-1] - path['s'][idx] < 0.1:
        return (0.0, 0.0, 0.0), idx, True

    # World velocity: feed-forward along the tangent plus correction towards the path
    v = 0.0 if idx == last else max(path['v'][idx], V_MIN)
    tangent = np.array([math.cos(path['theta'][idx]), math.sin(path['theta'][idx])])
    u = v * tangent + K_P * (pts[idx] - p)
    speed = np.linalg.norm(u)
    if speed > v_max:
        u = u * v_max / speed

    # Rotate into the body frame; yaw follows the path tangent
    vx = math.cos(th) * u[0] + math.sin(th) * u[1]
    vy = -math.sin(th) * u[0] + math.cos(th) * u[1]
    wz = v * path['kappa'][idx] + K_THETA * wrap(path['theta'][idx] - th)
    wz = max(-W_MAX, min(W_MAX, wz))
    return (vx, vy, wz), idx, False


def rotate_step(target, pose):
    """One iteration of the in-place rotation controller (pure function).

    :param target: target heading (rad).
    :param pose: (x, y, theta) of the robot.
    :return: body-frame command (vx, vy, wz), done flag.
    """
    err = wrap(target - pose[2])
    if abs(err) < YAW_TOL:
        return (0.0, 0.0, 0.0), True
    wz = max(-W_MAX, min(W_MAX, K_THETA * err))
    return (0.0, 0.0, wz), False


class Navigator:
    """Follow smooth paths with closed-loop drive_speed commands."""

    def __init__(self, ep_robot, v_max=0.4):
        """Subscribe to the robot sensors and set the chassis-lead mode.

        :param ep_robot: connected RoboMaster object.
        :param v_max: max speed (m/s), keep it <= 0.5.
        """
        self.ep_robot = ep_robot
        self.chassis = ep_robot.chassis
        self.v_max = v_max
        self.lock = threading.Lock()
        self.position = None
        self.yaw = None
        self.distance = float('inf')
        self.impact = False
        self.origin = None

        # Sensor subscriptions (callbacks run on the SDK thread)
        self.chassis.sub_position(cs=1, freq=20, callback=self._on_position)
        self.chassis.sub_attitude(freq=20, callback=self._on_attitude)
        self.chassis.sub_status(freq=20, callback=self._on_status)
        ep_robot.sensor.sub_distance(freq=20, callback=self._on_distance)

        # The gimbal follows the chassis, so the camera looks where the robot goes
        self.prev_mode = ep_robot.get_robot_mode()
        ep_robot.set_robot_mode(robot.CHASSIS_LEAD)

    def _on_position(self, info):
        with self.lock:
            self.position = (info[0], Y_SIGN_FEEDBACK * info[1])

    def _on_attitude(self, info):
        with self.lock:
            self.yaw = YAW_SIGN_FEEDBACK * math.radians(info[0])

    def _on_status(self, info):
        with self.lock:
            self.impact = self.impact or any(info[6:9])

    def _on_distance(self, info):
        with self.lock:
            self.distance = info[TOF_INDEX] / 1000

    def _pose(self):
        """Latest pose in the frame of the robot when follow() started.

        :return: (x, y, theta) in m, m, rad.
        """
        with self.lock:
            (x, y), yaw = self.position, self.yaw
        x0, y0, yaw0 = self.origin
        dx, dy = x - x0, y - y0
        c, s = math.cos(yaw0), math.sin(yaw0)
        return c * dx + s * dy, -s * dx + c * dy, wrap(yaw - yaw0)

    def _send(self, vx, vy, wz):
        """Send a body-frame velocity command, converting to SDK units and signs."""
        # drive_speed is fire-and-forget: the SDK always returns False (no ack), so ignore it
        self.chassis.drive_speed(x=vx, y=Y_SIGN_CMD * vy, z=YAW_SIGN_CMD * math.degrees(wz),
                                 timeout=3 / RATE)

    def plan(self, commands):
        """Plan a list of commands, see plan(). No motion."""
        return plan(commands, v_max=self.v_max)

    def follow(self, steps, timeout=60):
        """Execute planned steps. Blocks until done; always stops the robot on error.

        :param steps: output of plan().
        :param timeout: max time for the whole motion (s).
        """
        # Wait for the first sensor readings and take the current pose as origin
        while self.position is None or self.yaw is None:
            time.sleep(0.05)
        with self.lock:
            self.origin = (self.position[0], self.position[1], self.yaw)

        t_start = time.time()
        try:
            for kind, target in steps:
                idx, done = 0, False
                while not done:
                    t_loop = time.time()

                    # Safety checks
                    with self.lock:
                        impact, distance = self.impact, self.distance
                    if impact:
                        raise RuntimeError('Impact detected')
                    if time.time() - t_start > timeout:
                        raise RuntimeError('Navigation timeout')

                    # Compute and send the command
                    pose = self._pose()
                    if kind == 'path':
                        cmd, idx, done = track_step(target, pose, idx, self.v_max)
                    else:
                        cmd, done = rotate_step(target, pose)
                    if cmd[0] > 0 and distance < MIN_DIST:
                        raise RuntimeError('Obstacle at {:.2f} m'.format(distance))
                    self._send(*cmd)
                    time.sleep(max(0, 1 / RATE - (time.time() - t_loop)))
        finally:
            self.chassis.drive_speed(x=0, y=0, z=0)

    def close(self):
        """Stop, unsubscribe and restore the robot mode."""
        self.chassis.drive_speed(x=0, y=0, z=0)
        self.chassis.unsub_position()
        self.chassis.unsub_attitude()
        self.chassis.unsub_status()
        self.ep_robot.sensor.unsub_distance()
        self.ep_robot.set_robot_mode(self.prev_mode)


def plot_path(steps, filename='path.png'):
    """Save a plot of the planned path and its speed profile.

    :param steps: output of plan().
    :param filename: output image file.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    for kind, path in steps:
        if kind != 'path':
            continue
        sc = ax1.scatter(path['y'], path['x'], c=path['v'], s=3, cmap='viridis')
        ax2.plot(path['s'], path['v'])
        fig.colorbar(sc, ax=ax1, label='v (m/s)')
    ax1.set_xlabel('y, left (m)')
    ax1.set_ylabel('x, forward (m)')
    ax1.invert_xaxis()
    ax1.set_aspect('equal')
    ax2.set_xlabel('s (m)')
    ax2.set_ylabel('v (m/s)')
    fig.tight_layout()
    fig.savefig(filename)


def sign_test(ep_robot):
    """Drive +x, +y and +z for 1 s each and print the feedback, to fix the sign constants."""
    ep_chassis = ep_robot.chassis
    ep_chassis.sub_position(cs=0, freq=10, callback=lambda p: print('position', p))
    ep_chassis.sub_attitude(freq=10, callback=lambda a: print('attitude', a))
    for x, y, z in [(0.2, 0, 0), (0, 0.2, 0), (0, 0, 30)]:
        print('drive_speed x={} y={} z={}'.format(x, y, z))
        ep_chassis.drive_speed(x=x, y=y, z=z, timeout=2)
        time.sleep(1)
        ep_chassis.drive_speed(x=0, y=0, z=0)
        time.sleep(1)
    ep_chassis.unsub_position()
    ep_chassis.unsub_attitude()


if __name__ == '__main__':

    # Connect the robot
    ep_robot = connect('wifi')

    # Run `python navigate.py sign` once to check the sign constants
    if len(sys.argv) > 1 and sys.argv[1] == 'sign':
        sign_test(ep_robot)
        ep_robot.close()
        sys.exit()

    # Plan a simple L-shaped route and save a plot to inspect it
    commands = [('forward', 1.5), ('left', 135), ('forward', 1.0), ('right', 90), ('forward', 1.0)]
    nav = Navigator(ep_robot, v_max=1.0)
    steps = nav.plan(commands)
    plot_path(steps)

    # Follow it, always leaving the robot stopped
    try:
        ep_robot.led.set_led(comp=led.COMP_ALL, r=0, g=255, b=0, effect=led.EFFECT_ON)
        nav.follow(steps)
    finally:
        nav.close()
        ep_robot.led.set_led(comp=led.COMP_ALL, r=0, g=0, b=0, effect=led.EFFECT_OFF)

    # End connection
    ep_robot.close()

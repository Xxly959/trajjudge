"""Supported OpenJudge score scales, shared by the runner and offline export."""

SCALES = {
    "trajectory_accuracy": (1.0, 3.0),
    "trajectory_comprehensive": (0.0, 1.0),
    "action_loop_detection": (0.0, 1.0),
    "observation_information_gain": (0.0, 1.0),
}

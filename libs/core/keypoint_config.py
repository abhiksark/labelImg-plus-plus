# libs/core/keypoint_config.py
"""COCO 17-point human pose keypoint skeleton template."""

COCO_KEYPOINT_NAMES = [
    'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
    'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
    'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
    'left_knee', 'right_knee', 'left_ankle', 'right_ankle',
]

COCO_SKELETON = [
    (15, 13), (13, 11), (16, 14), (14, 12), (11, 12),
    (5, 11), (6, 12),
    (5, 7), (7, 9), (6, 8), (8, 10),
    (1, 2), (1, 3), (2, 4), (3, 5), (4, 6), (0, 1), (0, 2),
]

COCO_KEYPOINT_COLORS = {
    'head': '#ff6b6b',
    'shoulder': '#96ceb4',
    'arm': '#ffd93d',
    'wrist': '#ff8a5c',
    'hip': '#a8e6cf',
    'leg': '#dda0dd',
    'ankle': '#87ceeb',
}

_INDEX_TO_REGION = {
    0: 'head', 1: 'head', 2: 'head', 3: 'head', 4: 'head',
    5: 'shoulder', 6: 'shoulder',
    7: 'arm', 8: 'arm',
    9: 'wrist', 10: 'wrist',
    11: 'hip', 12: 'hip',
    13: 'leg', 14: 'leg',
    15: 'ankle', 16: 'ankle',
}


def get_keypoint_color(index):
    """Return the hex color string for a keypoint by its index (0-16)."""
    region = _INDEX_TO_REGION.get(index, 'head')
    return COCO_KEYPOINT_COLORS[region]

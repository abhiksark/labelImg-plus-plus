# libs/core/keypoint_config.py
"""Keypoint skeleton template registry.

Supports multiple keypoint templates (e.g., COCO human pose, face landmarks).
Each template defines keypoint names, skeleton connections, and colors.
"""


KEYPOINT_TEMPLATES = {
    'person': {
        'names': [
            'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
            'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
            'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
            'left_knee', 'right_knee', 'left_ankle', 'right_ankle',
        ],
        'skeleton': [
            (15, 13), (13, 11), (16, 14), (14, 12), (11, 12),
            (5, 11), (6, 12),
            (5, 7), (7, 9), (6, 8), (8, 10),
            (1, 2), (1, 3), (2, 4), (3, 5), (4, 6), (0, 1), (0, 2),
        ],
        'colors': {
            'head': '#ff6b6b',
            'shoulder': '#96ceb4',
            'arm': '#ffd93d',
            'wrist': '#ff8a5c',
            'hip': '#a8e6cf',
            'leg': '#dda0dd',
            'ankle': '#87ceeb',
        },
        'index_to_region': {
            0: 'head', 1: 'head', 2: 'head', 3: 'head', 4: 'head',
            5: 'shoulder', 6: 'shoulder',
            7: 'arm', 8: 'arm',
            9: 'wrist', 10: 'wrist',
            11: 'hip', 12: 'hip',
            13: 'leg', 14: 'leg',
            15: 'ankle', 16: 'ankle',
        },
    },
    'face': {
        'names': [
            'left_eye', 'right_eye', 'nose', 'left_mouth', 'right_mouth',
        ],
        'skeleton': [
            (0, 2), (1, 2), (3, 4),
        ],
        'colors': {
            'eye': '#4ecdc4',
            'nose': '#ff6b6b',
            'mouth': '#ffd93d',
        },
        'index_to_region': {
            0: 'eye', 1: 'eye',
            2: 'nose',
            3: 'mouth', 4: 'mouth',
        },
    },
}

# Backward-compatible aliases for the COCO human pose template
COCO_KEYPOINT_NAMES = KEYPOINT_TEMPLATES['person']['names']
COCO_SKELETON = KEYPOINT_TEMPLATES['person']['skeleton']
COCO_KEYPOINT_COLORS = KEYPOINT_TEMPLATES['person']['colors']


def get_template(label):
    """Return the keypoint template for a given label, or None."""
    return KEYPOINT_TEMPLATES.get(label.lower())


def get_keypoint_color(index, template_name='person'):
    """Return the hex color string for a keypoint by index and template."""
    template = KEYPOINT_TEMPLATES.get(template_name)
    if not template:
        return '#888888'
    region = template['index_to_region'].get(index, 'head')
    return template['colors'].get(region, '#888888')

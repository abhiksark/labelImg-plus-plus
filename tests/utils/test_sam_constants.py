from libs.utils import constants


def test_sam_setting_keys_exist_and_are_namespaced():
    assert constants.SETTING_SAM_CHECKPOINT == 'sam/checkpoint'
    assert constants.SETTING_SAM_MODEL_TYPE == 'sam/modelType'
    assert constants.SETTING_SAM_DEVICE == 'sam/device'

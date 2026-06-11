from libs.utils import constants


def test_legacy_torch_setting_keys_are_gone():
    assert not hasattr(constants, 'SETTING_SAM_CHECKPOINT')
    assert not hasattr(constants, 'SETTING_SAM_MODEL_TYPE')
    assert not hasattr(constants, 'SETTING_SAM_DEVICE')


def test_onnx_sam_setting_keys_exist_and_are_namespaced():
    assert constants.SETTING_SAM_ENCODER == 'sam/encoderPath'
    assert constants.SETTING_SAM_DECODER == 'sam/decoderPath'

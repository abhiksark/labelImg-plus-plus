from libs.utils import constants


def test_legacy_torch_setting_keys_are_gone():
    assert not hasattr(constants, 'SETTING_SAM_CHECKPOINT')
    assert not hasattr(constants, 'SETTING_SAM_MODEL_TYPE')
    assert not hasattr(constants, 'SETTING_SAM_DEVICE')


def test_onnx_sam_setting_keys_exist_and_are_namespaced():
    assert constants.SETTING_SAM_ENCODER == 'sam/encoderPath'
    assert constants.SETTING_SAM_DECODER == 'sam/decoderPath'
    assert constants.SETTING_SAM_OUTPUT_MODE == 'sam/outputMode'


def test_video_sam2_setting_keys_are_namespaced():
    assert constants.SETTING_VIDEO_PROPAGATION_BACKEND \
        == 'video/propagationBackend'
    assert constants.SETTING_VIDEO_SAM2_CHECKPOINT == 'video/sam2Checkpoint'
    assert constants.SETTING_VIDEO_SAM2_CONFIG == 'video/sam2Config'

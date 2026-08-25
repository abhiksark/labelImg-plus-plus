from dataclasses import FrozenInstanceError

import pytest

from libs.integrations.model_manifest import (
    MOBILE_SAM_MANIFEST,
    ModelArtifact,
    ModelManifest,
)


def test_mobile_sam_manifest_is_complete():
    assert MOBILE_SAM_MANIFEST.provider == 'LabelImg++ GitHub Releases'
    assert MOBILE_SAM_MANIFEST.total_size > 0
    assert len(MOBILE_SAM_MANIFEST.artifacts) == 2
    assert all(len(item.sha256) == 64 and item.size > 0
               for item in MOBILE_SAM_MANIFEST.artifacts)


def test_mobile_sam_manifest_has_authoritative_metadata():
    assert MOBILE_SAM_MANIFEST.model_id == 'mobile-sam-onnx-v1'
    assert MOBILE_SAM_MANIFEST.display_name == 'MobileSAM'
    assert MOBILE_SAM_MANIFEST.purpose == (
        'Turn box or point prompts into object masks')
    assert [item.name for item in MOBILE_SAM_MANIFEST.artifacts] == [
        'mobile_sam.encoder.onnx', 'mobile_sam.decoder.onnx']
    assert [item.size for item in MOBILE_SAM_MANIFEST.artifacts] == [
        28157203, 16501737]
    assert MOBILE_SAM_MANIFEST.total_size == 44658940


def test_manifest_artifacts_are_pinned_to_existing_release_urls():
    assert [item.url for item in MOBILE_SAM_MANIFEST.artifacts] == [
        ('https://github.com/abhiksark/labelImg-plus-plus/releases/download/'
         'sam-onnx-v1/mobile_sam.encoder.onnx'),
        ('https://github.com/abhiksark/labelImg-plus-plus/releases/download/'
         'sam-onnx-v1/mobile_sam.decoder.onnx'),
    ]
    assert [item.sha256 for item in MOBILE_SAM_MANIFEST.artifacts] == [
        '801d81952ee19217632966f7cfe07a8030c115a7fe5bfbec9294bfaf95e44a45',
        '001f6386a4c6036f6fac6a104d18d7c008c7eb188b2936dab749e34cae33e1c8',
    ]


def test_manifest_and_artifacts_are_immutable():
    artifact = MOBILE_SAM_MANIFEST.artifacts[0]
    with pytest.raises(FrozenInstanceError):
        artifact.size = 0
    with pytest.raises(FrozenInstanceError):
        MOBILE_SAM_MANIFEST.provider = 'other'
    assert isinstance(MOBILE_SAM_MANIFEST.artifacts, tuple)
    assert isinstance(artifact, ModelArtifact)
    assert isinstance(MOBILE_SAM_MANIFEST, ModelManifest)

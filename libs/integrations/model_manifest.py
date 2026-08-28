"""Immutable provider metadata for downloadable Assist model artifacts."""

from dataclasses import dataclass


MOBILE_SAM_ENCODER_URL = (
    'https://github.com/abhiksark/labelImg-plus-plus/releases/download/'
    'sam-onnx-v1/mobile_sam.encoder.onnx')
MOBILE_SAM_DECODER_URL = (
    'https://github.com/abhiksark/labelImg-plus-plus/releases/download/'
    'sam-onnx-v1/mobile_sam.decoder.onnx')


@dataclass(frozen=True)
class ModelArtifact:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelManifest:
    model_id: str
    display_name: str
    purpose: str
    provider: str
    artifacts: tuple

    @property
    def total_size(self):
        return sum(item.size for item in self.artifacts)


MOBILE_SAM_MANIFEST = ModelManifest(
    model_id='mobile-sam-onnx-v1',
    display_name='MobileSAM',
    purpose='Turn box or point prompts into object masks',
    provider='LabelImg++ GitHub Releases',
    artifacts=(
        ModelArtifact(
            'mobile_sam.encoder.onnx', MOBILE_SAM_ENCODER_URL,
            28157203,
            '801d81952ee19217632966f7cfe07a8030c115a7fe5bfbec9294bfaf95e44a45'),
        ModelArtifact(
            'mobile_sam.decoder.onnx', MOBILE_SAM_DECODER_URL,
            16501737,
            '001f6386a4c6036f6fac6a104d18d7c008c7eb188b2936dab749e34cae33e1c8'),
    ),
)

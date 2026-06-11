# scripts/export_sam_onnx.py
"""Export the MobileSAM checkpoint to the ONNX encoder/decoder pair we host.

Maintainer-only; the app never imports this. Run inside a throwaway venv:

    pip install torch torchvision samexporter onnxscript \\
        git+https://github.com/facebookresearch/segment-anything.git \\
        git+https://github.com/ChaoningZhang/MobileSAM.git
    python scripts/export_sam_onnx.py mobile_sam.pt output_dir/

Upload the two outputs as GitHub Release assets under tag sam-onnx-v1 and
make sure the printed SHA256 digests match the pins in
libs/integrations/model_cache.py.

Gotchas encoded below (verified 2026-06-11, torch 2.12 / samexporter):
- samexporter's encoder wants model_type "mobile" for MobileSAM (its README
  says vit_t, which raises KeyError).
- samexporter's decoder only knows the official segment_anything registry,
  so mobile_sam's vit_t entry is patched in.
- torch >= 2.12 defaults torch.onnx.export to the dynamo exporter, which
  rejects samexporter's file-handle output; the legacy exporter is forced.
"""

import hashlib
import os
import sys

EXPECTED_CHECKPOINT_SHA256 = (
    "6dbb90523a35330fedd7f1d3dfc66f995213d81b29a5ca8108dbcdd4e37d6c2f")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/export_sam_onnx.py "
                 "<mobile_sam.pt> <output_dir>")
    checkpoint, out_dir = sys.argv[1], sys.argv[2]
    actual = _sha256(checkpoint)
    if actual != EXPECTED_CHECKPOINT_SHA256:
        sys.exit("checkpoint sha256 %s does not match the official "
                 "mobile_sam.pt" % actual)
    os.makedirs(out_dir, exist_ok=True)

    import torch
    original_export = torch.onnx.export

    def legacy_export(*args, **kwargs):
        kwargs.setdefault("dynamo", False)
        return original_export(*args, **kwargs)

    torch.onnx.export = legacy_export

    import samexporter.export_decoder as export_decoder
    import samexporter.export_encoder as export_encoder
    from mobile_sam import sam_model_registry

    export_decoder.sam_model_registry["vit_t"] = sam_model_registry["vit_t"]

    encoder_out = os.path.join(out_dir, "mobile_sam.encoder.onnx")
    decoder_out = os.path.join(out_dir, "mobile_sam.decoder.onnx")
    export_encoder.run_export(
        model_type="mobile", checkpoint=checkpoint, output=encoder_out,
        use_preprocess=True, opset=17)
    export_decoder.run_export(
        model_type="vit_t", checkpoint=checkpoint, output=decoder_out,
        opset=17, return_single_mask=True)

    for path in (encoder_out, decoder_out):
        print("%s  %s  (%d bytes)" % (
            _sha256(path), path, os.path.getsize(path)))


if __name__ == "__main__":
    main()

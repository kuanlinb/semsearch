"""Make the int8 ONNX model used by embed_backend "onnx" from the fp32 ONNX export of bge-m3.

    python tools/export_onnx.py <fp32 dir> <out dir>     (needs: pip install onnx onnxruntime)

<fp32 dir> holds model.onnx + model.onnx_data and tokenizer.json, e.g. from Xenova/bge-m3 (onnx/).
Weights are quantized per output channel (vectors stay at cosine ~0.993 to the PyTorch ones;
per-tensor int8 only reaches ~0.988) and saved to a separate model.onnx_data file, which
ONNX Runtime memory-maps instead of copying (about half the resident memory).
"""
import os
import shutil
import sys
import tempfile

import onnx
from onnxruntime.quantization import QuantType, quantize_dynamic

src, out = sys.argv[1:3]
os.makedirs(out, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    q = os.path.join(tmp, "q.onnx")
    quantize_dynamic(os.path.join(src, "model.onnx"), q, per_channel=True, weight_type=QuantType.QInt8,
                     op_types_to_quantize=["MatMul", "Gather"], extra_options={"MatMulConstBOnly": True})
    onnx.save_model(onnx.load(q), os.path.join(out, "model.onnx"), save_as_external_data=True,
                    all_tensors_to_one_file=True, location="model.onnx_data", size_threshold=1024)
shutil.copy(os.path.join(src, "tokenizer.json"), out)
print("wrote", out)

"""Export a cross-encoder (default BAAI/bge-reranker-v2-m3) to fp32 ONNX, for tools/export_onnx.py.

    python eval/local_rerank/export_reranker.py <out dir> [model]     (needs: torch, transformers, onnx)

Writes model.onnx + model.onnx_data (inputs input_ids, attention_mask; output logits) and tokenizer.json.
"""
import os
import sys

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

out = sys.argv[1]
name = sys.argv[2] if len(sys.argv) > 2 else "BAAI/bge-reranker-v2-m3"
os.makedirs(out, exist_ok=True)
tok = AutoTokenizer.from_pretrained(name)
model = AutoModelForSequenceClassification.from_pretrained(name, attn_implementation="eager").eval()
x = tok(["a question"] * 2, ["some passage text"] * 2, return_tensors="pt", padding=True)


class Wrap(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, input_ids, attention_mask):
        return self.m(input_ids=input_ids, attention_mask=attention_mask).logits


torch.onnx.export(Wrap(model), (x["input_ids"], x["attention_mask"]), os.path.join(out, "model.onnx"),
                  input_names=["input_ids", "attention_mask"], output_names=["logits"],
                  dynamic_shapes=None, dynamic_axes={"input_ids": {0: "b", 1: "t"}, "attention_mask": {0: "b", 1: "t"},
                                "logits": {0: "b"}}, opset_version=18, dynamo=True,
                  external_data=True)
tok.backend_tokenizer.save(os.path.join(out, "tokenizer.json"))
print("wrote", out)

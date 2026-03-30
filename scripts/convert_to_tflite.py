"""
convert_to_tflite.py  (v7 - litert-torch, pure PyTorch -> TFLite)
==================================================================
No ONNX. No TF. Just torch -> TFLite via litert-torch.
"""
import argparse, os
import torch

parser = argparse.ArgumentParser()
parser.add_argument("--model_dir", default="models/tinybert_poison_classifier_v2")
parser.add_argument("--output",    default="android/prism-shield-service/app/src/main/assets/tinybert_prism.tflite")
parser.add_argument("--seq_len",   type=int, default=128)
args = parser.parse_args()

SEQ_LEN = args.seq_len

print("[1/3] Loading model from", args.model_dir)
from transformers import AutoModelForSequenceClassification
model = AutoModelForSequenceClassification.from_pretrained(args.model_dir)
model.eval()

print("[2/3] Converting PyTorch -> TFLite via litert-torch ...")
import litert.torch as litert_torch

sample_ids  = torch.zeros(1, SEQ_LEN, dtype=torch.long)
sample_mask = torch.ones(1,  SEQ_LEN, dtype=torch.long)
sample_type = torch.zeros(1, SEQ_LEN, dtype=torch.long)

edge_model = litert_torch.convert(
    model,
    (sample_ids, sample_mask, sample_type),
)

print("[3/3] Saving to", args.output)
os.makedirs(os.path.dirname(args.output), exist_ok=True)
edge_model.export(args.output)

size_kb = os.path.getsize(args.output) / 1024
print("\nDone. Model size: %.1f KB" % size_kb)
print("Output ->", args.output)

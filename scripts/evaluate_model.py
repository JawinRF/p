import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

MODEL_PATH = "models/tinybert_poison_classifier"
DATA_PATH = "data/tinybert_training_dataset.parquet"

df = pd.read_parquet(DATA_PATH)

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)

model.eval()
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)

texts = df["text"].tolist()
labels = df["label"].tolist()

batch_size = 64
preds = []

for i in range(0, len(texts), batch_size):
    batch = texts[i:i+batch_size]

    inputs = tokenizer(
        batch,
        padding=True,
        truncation=True,
        max_length=128,
        return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    batch_preds = torch.argmax(logits, dim=1).cpu().tolist()
    preds.extend(batch_preds)

accuracy = accuracy_score(labels, preds)
precision, recall, f1, _ = precision_recall_fscore_support(labels, preds, average="binary")

print("\nEvaluation Metrics")
print("------------------")
print("Accuracy:", accuracy)
print("Precision:", precision)
print("Recall:", recall)
print("F1:", f1)

# Attack Success Rate
poison_indices = [i for i,l in enumerate(labels) if l == 1]

poison_total = len(poison_indices)
poison_missed = sum(1 for i in poison_indices if preds[i] == 0)

asr = poison_missed / poison_total

print("\nAttack Success Rate (ASR)")
print("-------------------------")
print("Poison samples:", poison_total)
print("Missed poisons:", poison_missed)
print("ASR:", asr)

"""
SHADOW — Classifier Evaluation Script.
Evaluates model on held-out test split and the manually curated StreamCove benchmark.
Reports Precision, Recall, F1, Confusion Matrix, FP, and FN.
"""
import json
import joblib
from pathlib import Path
from sklearn.metrics import classification_report, confusion_matrix

ROOT_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT_DIR / "backend" / "models" / "dark_pattern_classifier.joblib"
STREAMCOVE_TEST_PATH = ROOT_DIR / "training" / "data" / "held_out_streamcove_test.json"


def evaluate_streamcove_benchmark():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Trained model not found at {MODEL_PATH}. Run train_classifier.py first.")

    artifact = joblib.load(MODEL_PATH)
    binary_model = artifact["binary_model"]
    category_model = artifact.get("category_model")

    print("=" * 65)
    print("EVALUATION ON HELD-OUT STREAMCOVE SUBSCRIPTION BENCHMARK")
    print("=" * 65)

    with open(STREAMCOVE_TEST_PATH, "r", encoding="utf-8") as f:
        benchmark = json.load(f)

    texts = [item["text"] for item in benchmark]
    y_true = [item["label"] for item in benchmark]
    expected_categories = [item["category"] for item in benchmark]

    y_pred = binary_model.predict(texts)
    y_probs = binary_model.predict_proba(texts)[:, 1]

    false_positives = []
    false_negatives = []
    correct = 0

    print(f"\nTotal test samples: {len(benchmark)}\n")
    for i, item in enumerate(benchmark):
        pred_label = int(y_pred[i])
        prob = float(y_probs[i])
        true_label = int(y_true[i])

        status = "✓ PASS" if pred_label == true_label else "✗ FAIL"
        if pred_label == true_label:
            correct += 1
        elif pred_label == 1 and true_label == 0:
            false_positives.append((item["text"], prob))
        elif pred_label == 0 and true_label == 1:
            false_negatives.append((item["text"], prob))

        pred_str = "Dark Pattern" if pred_label == 1 else "Not Dark Pattern"
        true_str = "Dark Pattern" if true_label == 1 else "Not Dark Pattern"

        print(f"[{status}] Prob: {prob:.3f} | Pred: {pred_str:<16} | True: {true_str:<16} | Snippet: {repr(item['text'][:60])}")

    acc = correct / len(benchmark)
    print("\n" + "-" * 50)
    print(f"StreamCove Benchmark Accuracy: {acc * 100:.1f}% ({correct}/{len(benchmark)})")
    print(f"False Positives ({len(false_positives)}):")
    for fp, p in false_positives:
        print(f"  - (p={p:.3f}) {fp}")
    print(f"False Negatives ({len(false_negatives)}):")
    for fn, p in false_negatives:
        print(f"  - (p={p:.3f}) {fn}")

    cm = confusion_matrix(y_true, y_pred).tolist()
    print(f"\nConfusion Matrix (TN, FP / FN, TP):\n{cm}")
    print("\nClassification Report:")
    print(classification_report(y_true, y_pred, target_names=["Not Dark Pattern", "Dark Pattern"]))

    return {
        "accuracy": acc,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "confusion_matrix": cm,
    }


if __name__ == "__main__":
    evaluate_streamcove_benchmark()

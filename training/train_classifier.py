"""
SHADOW — Local Dark Pattern Classifier Training Pipeline.
Uses the academic dataset from Yamanalab EC Darkpattern (Apache-2.0 License).
Trains a TF-IDF + Logistic Regression model for real-time local inference.
"""
import os
import sys
import csv
import json
from pathlib import Path
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT_DIR / "training" / "data" / "ec_darkpattern.tsv"
MODEL_DIR = ROOT_DIR / "backend" / "models"
MODEL_PATH = MODEL_DIR / "dark_pattern_classifier.joblib"
METADATA_PATH = MODEL_DIR / "model_metadata.json"


def load_and_deduplicate_dataset(filepath: Path):
    if not filepath.exists():
        raise FileNotFoundError(f"Dataset not found at {filepath}")

    raw_rows = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for r in reader:
            if len(r) >= 4:
                raw_rows.append(r[:4])

    print(f"[Dataset] Total raw rows: {len(raw_rows)}")

    # Deduplication to avoid data leakage
    seen_texts = set()
    cleaned_data = []
    duplicates_removed = 0

    for r in raw_rows:
        text = r[1].strip()
        normalized_text = " ".join(text.lower().split())
        if not normalized_text:
            continue
        if normalized_text in seen_texts:
            duplicates_removed += 1
            continue
        seen_texts.add(normalized_text)

        try:
            label = int(r[2].strip())
        except ValueError:
            continue
        category = r[3].strip()
        cleaned_data.append({
            "text": text,
            "label": label,
            "category": category,
        })

    print(f"[Dataset] Unique rows: {len(cleaned_data)} (removed {duplicates_removed} duplicates)")
    return cleaned_data


def train_model():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    dataset = load_and_deduplicate_dataset(DATA_PATH)

    texts = [d["text"] for d in dataset]
    labels = [d["label"] for d in dataset]
    categories = [d["category"] for d in dataset]

    # Proper 80/20 train/test split with stratification
    X_train, X_test, y_train, y_test, cat_train, cat_test = train_test_split(
        texts, labels, categories, test_size=0.20, random_state=42, stratify=labels
    )

    print(f"[Split] Train samples: {len(X_train)} | Test samples: {len(X_test)}")

    # Binary Pipeline: TF-IDF + Logistic Regression
    pipeline = Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=4000,
                sublinear_tf=True,
                stop_words="english",
            ),
        ),
        (
            "clf",
            LogisticRegression(
                C=2.0,
                class_weight="balanced",
                max_iter=1000,
                random_state=42,
            ),
        ),
    ])

    print("[Training] Fitting TF-IDF + Logistic Regression binary classifier...")
    pipeline.fit(X_train, y_train)

    # Evaluate on held-out test split
    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)[:, 1]

    prec, rec, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="binary")
    cm = confusion_matrix(y_test, y_pred).tolist()

    report = classification_report(y_test, y_pred, target_names=["Not Dark Pattern", "Dark Pattern"], output_dict=True)

    print("\n" + "=" * 50)
    print("BINARY CLASSIFICATION REPORT (Test Split)")
    print("=" * 50)
    print(classification_report(y_test, y_pred, target_names=["Not Dark Pattern", "Dark Pattern"]))
    print(f"Confusion Matrix (TN, FP / FN, TP):\n{cm}")

    # Train category classifier on dark patterns subset for category suggestion
    dp_indices = [i for i, y in enumerate(y_train) if y == 1 and cat_train[i] != "Not Dark Pattern"]
    dp_texts = [X_train[i] for i in dp_indices]
    dp_cats = [cat_train[i] for i in dp_indices]

    category_pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=3000, stop_words="english")),
        ("clf", LogisticRegression(C=1.5, class_weight="balanced", max_iter=1000, random_state=42)),
    ])
    category_pipeline.fit(dp_texts, dp_cats)

    # Bundle and save artifact
    artifact = {
        "binary_model": pipeline,
        "category_model": category_pipeline,
        "version": "1.0.0",
        "dataset_source": "https://github.com/yamanalab/ec-darkpattern",
        "license": "Apache-2.0",
    }
    joblib.dump(artifact, MODEL_PATH)
    print(f"\n[Saved] Model artifact saved to: {MODEL_PATH}")

    # Save metadata
    metadata = {
        "model_type": "TF-IDF (1-2 grams) + Logistic Regression",
        "dataset": "Yamanalab EC Darkpattern",
        "license": "Apache-2.0",
        "total_unique_samples": len(dataset),
        "test_size": len(X_test),
        "metrics": {
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1_score": round(float(f1), 4),
            "confusion_matrix": cm,
            "full_report": report,
        },
        "hyperparameters": {
            "tfidf_ngram_range": [1, 2],
            "tfidf_max_features": 4000,
            "clf_C": 2.0,
            "class_weight": "balanced",
        },
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"[Saved] Metadata saved to: {METADATA_PATH}")

    return artifact, metadata


if __name__ == "__main__":
    train_model()

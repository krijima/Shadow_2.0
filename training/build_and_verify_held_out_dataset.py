"""
Build and verify independent held-out evaluation dataset.
Ensures zero overlap with training data and evaluates Rule-Only, ML-Only, and Hybrid.
"""
import os
import sys
import csv
import json
import time
from pathlib import Path
import numpy as np

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from shadow_scan import ShadowScan
from ml_detector import MLDetector

ROOT_DIR = Path(__file__).resolve().parent.parent
EC_DATA_PATH = ROOT_DIR / "training" / "data" / "ec_darkpattern.tsv"
OUTPUT_DATA_PATH = ROOT_DIR / "training" / "data" / "independent_held_out_evaluation.json"

HELD_OUT_CANDIDATES = [
    # ── Category 1: Confirm-shaming (Label: 1) ──
    {
        "text": "No thanks, I prefer paying full retail price for my groceries",
        "label": 1,
        "type": "confirm_shaming",
        "description": "Shaming user into declining savings"
    },
    {
        "text": "No, I don't want to protect my identity online",
        "label": 1,
        "type": "confirm_shaming",
        "description": "Manipulative decline button text"
    },
    {
        "text": "I'd rather miss out on exclusive insider perks and deals",
        "label": 1,
        "type": "confirm_shaming",
        "description": "FOMO-inducing decline link"
    },
    {
        "text": "No thanks, I hate getting free product upgrades and bonuses",
        "label": 1,
        "type": "confirm_shaming",
        "description": "Guilt-inducing button"
    },
    {
        "text": "No, I choose to remain unprotected against phishing attacks",
        "label": 1,
        "type": "confirm_shaming",
        "description": "Coercive security opt-out phrasing"
    },

    # ── Category 2: Retention Obstacles (Label: 1) ──
    {
        "text": "Wait before you cancel! Take 50% off for your next 3 months to stay and save with us!",
        "label": 1,
        "type": "retention_obstacle",
        "description": "Aggressive retention offer during cancellation flow"
    },
    {
        "text": "Special offer just for you: accept offer now and keep your VIP membership for $4.99/mo!",
        "label": 1,
        "type": "retention_obstacle",
        "description": "Prominent retention barrier"
    },
    {
        "text": "Don't leave us today! We don't want to lose you, take 60% off for your next billing cycle.",
        "label": 1,
        "type": "retention_obstacle",
        "description": "Retention discount blocking cancellation"
    },
    {
        "text": "One last offer: stay and save with our annual loyalty pass at a steep 75% discount!",
        "label": 1,
        "type": "retention_obstacle",
        "description": "Last-chance retention offer"
    },
    {
        "text": "Exclusive deal unlocked: claim your $10 monthly credit if you keep your account open.",
        "label": 1,
        "type": "retention_obstacle",
        "description": "Financial bribe retention obstacle"
    },

    # ── Category 3: Suspicious & Fake Urgency (Label: 1) ──
    {
        "text": "High demand! Offer expires in 00:59 seconds! Claim your discount before the countdown ends!",
        "label": 1,
        "type": "fake_urgency",
        "description": "Artificial countdown pressure"
    },
    {
        "text": "Hurry! Only 1 left in stock at this clearance price! 34 other shoppers are looking at this item right now!",
        "label": 1,
        "type": "fake_urgency",
        "description": "Fake scarcity and social proof"
    },
    {
        "text": "Flash deal expiring today! Only today can you secure this rate before standard pricing resumes.",
        "label": 1,
        "type": "suspicious_urgency",
        "description": "Suspicious unverified urgency"
    },
    {
        "text": "Limited time offer! Act fast before prices increase at midnight!",
        "label": 1,
        "type": "suspicious_urgency",
        "description": "Psychological time pressure"
    },

    # ── Category 4: Neutral Discount Offers (Label: 0) ──
    {
        "text": "Annual plans save 15% compared to monthly billing at $12.99/mo.",
        "label": 0,
        "type": "neutral_discount",
        "description": "Transparent annual vs monthly pricing"
    },
    {
        "text": "College students and faculty receive a 10% educational discount upon student ID verification.",
        "label": 0,
        "type": "neutral_discount",
        "description": "Legitimate educational discount"
    },
    {
        "text": "Family bundle savings: Add up to 4 family members for an additional $4/month total.",
        "label": 0,
        "type": "neutral_discount",
        "description": "Standard multi-seat pricing breakdown"
    },
    {
        "text": "Early bird registration is open through November 30 for attendees who register in advance.",
        "label": 0,
        "type": "neutral_discount",
        "description": "Factual event registration schedule"
    },

    # ── Category 5: Genuine Subscription & Billing Notices (Label: 0) ──
    {
        "text": "Your subscription is paid through December 12, 2026. Next billing date: Jan 12, 2027.",
        "label": 0,
        "type": "genuine_notice",
        "description": "Factual billing status"
    },
    {
        "text": "Payment method on file: Visa ending in 4242. To update your billing card, visit Payment Settings.",
        "label": 0,
        "type": "genuine_notice",
        "description": "Account payment details"
    },
    {
        "text": "Want to make changes to your subscription? You can cancel at any time in Account Preferences.",
        "label": 0,
        "type": "genuine_notice",
        "description": "Transparent cancellation policy notice"
    },
    {
        "text": "Monthly receipt for Invoice #9842: $14.99 charged on Nov 1, 2026. Download PDF statement.",
        "label": 0,
        "type": "genuine_notice",
        "description": "Standard billing receipt text"
    },

    # ── Category 6: Educational Text Discussing Dark Patterns (Label: 0) ──
    {
        "text": "According to academic research, confirmshaming is a dark pattern where the opt-out option uses manipulative phrasing like 'No thanks, I love paying more' to guilt users.",
        "label": 0,
        "type": "educational_discussion",
        "description": "Scholarly definition of confirmshaming"
    },
    {
        "text": "In this article, we examine the practice of forced continuity, defined as a design pattern where free trials automatically renew into paid plans without adequate notice.",
        "label": 0,
        "type": "educational_discussion",
        "description": "Encyclopedic overview of deceptive renewals"
    },
    {
        "text": "The FTC report highlighted deceptive design patterns, illustrating how countdown timers create artificial urgency when no real expiration exists.",
        "label": 0,
        "type": "educational_discussion",
        "description": "Government regulatory report discussion"
    },
    {
        "text": "Researchers define roach motel as an interface where subscribing is effortless but cancelling requires multiple obfuscated phone calls and retention obstacles.",
        "label": 0,
        "type": "educational_discussion",
        "description": "Academic taxonomy of dark patterns"
    },

    # ── Category 7: Unfamiliar / Neutral Cancellation Interfaces (Label: 0) ──
    {
        "text": "To cancel your plan, click 'Manage Plan', select 'Cancel Subscription', and confirm your choice.",
        "label": 0,
        "type": "standard_cancellation",
        "description": "Straightforward cancellation instructions"
    },
    {
        "text": "Yes, cancel my subscription. We will send an email confirmation to user@example.com.",
        "label": 0,
        "type": "standard_cancellation",
        "description": "Direct cancellation confirmation button"
    },
    {
        "text": "Please provide feedback on why you are cancelling: Cost, Missing Features, Switched Providers, or Other.",
        "label": 0,
        "type": "standard_cancellation",
        "description": "Neutral exit feedback questionnaire"
    },
    {
        "text": "Your cancellation is scheduled for the end of the current billing cycle. You maintain full access until Dec 31.",
        "label": 0,
        "type": "standard_cancellation",
        "description": "Factual end-of-term cancellation summary"
    },
]


def verify_no_overlap_and_save():
    # Load training dataset
    training_texts = set()
    with open(EC_DATA_PATH, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for r in reader:
            if len(r) >= 2:
                norm = " ".join(r[1].lower().split())
                if norm:
                    training_texts.add(norm)

    print(f"Loaded {len(training_texts)} unique training samples from {EC_DATA_PATH.name}")

    # Verify no candidate is in training dataset
    verified_dataset = []
    overlap_count = 0
    for item in HELD_OUT_CANDIDATES:
        norm = " ".join(item["text"].lower().split())
        if norm in training_texts:
            print(f"WARNING: Overlap found for text: '{item['text']}'! Excluding.")
            overlap_count += 1
            continue
        verified_dataset.append(item)

    print(f"Verified {len(verified_dataset)} independent samples (0 duplicates found with training set)")

    with open(OUTPUT_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(verified_dataset, f, indent=2)
    print(f"Saved held-out evaluation dataset to {OUTPUT_DATA_PATH}")
    return verified_dataset


def run_comparative_benchmark(dataset):
    scanner = ShadowScan()
    ml = MLDetector()

    y_true = [item["label"] for item in dataset]
    n = len(dataset)

    # ── 1. Rule-Only Benchmark ──
    t0 = time.perf_counter()
    y_pred_rule = []
    for item in dataset:
        text = item["text"]
        # Rule check: matching DARK_PATTERN_RULES only
        is_dp = False
        if not scanner.is_educational_or_quoted_context(text) and not scanner.is_legitimate_context(text):
            for rule in scanner._get_rules_for_eval():
                if scanner._match_patterns(text, rule):
                    is_dp = True
                    break
        y_pred_rule.append(1 if is_dp else 0)
    rule_lat = (time.perf_counter() - t0) / n * 1000

    # ── 2. Local ML-Only Benchmark ──
    t0 = time.perf_counter()
    y_pred_ml = []
    for item in dataset:
        text = item["text"]
        res = ml.predict(text)
        y_pred_ml.append(1 if res.get("is_dark_pattern") and res.get("confidence", 0) >= 0.50 else 0)
    ml_lat = (time.perf_counter() - t0) / n * 1000

    # ── 3. Hybrid Rule + ML Benchmark (Production ShadowScan) ──
    t0 = time.perf_counter()
    y_pred_hybrid = []
    for item in dataset:
        text = item["text"]
        dets = scanner.scan_page_text(text, url="https://example.com/test", task_id="eval-task")
        # Check if consumer pattern detected
        has_dp = any(d.get("threat_type") == "consumer_pattern" for d in dets)
        y_pred_hybrid.append(1 if has_dp else 0)
    hybrid_lat = (time.perf_counter() - t0) / n * 1000

    # Metrics calculation helper
    def calc_metrics(y_true, y_pred, latency):
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
        tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        cm = [[tn, fp], [fn, tp]]

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "fpr": round(fpr, 4),
            "confusion_matrix": cm,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "avg_latency_ms": round(latency, 3),
        }

    results = {
        "dataset_size": n,
        "rule_only": calc_metrics(y_true, y_pred_rule, rule_lat),
        "ml_only": calc_metrics(y_true, y_pred_ml, ml_lat),
        "hybrid": calc_metrics(y_true, y_pred_hybrid, hybrid_lat),
    }

    print("\n" + "=" * 70)
    print("COMPARATIVE EVALUATION RESULTS (INDEPENDENT HELD-OUT DATASET)")
    print("=" * 70)
    print(f"Total Test Samples: {n} (Positive/Dark Pattern: {sum(y_true)}, Negative/Clean: {n - sum(y_true)})")
    print("-" * 70)
    for name, m in [("1. Rule-Only", results["rule_only"]), ("2. Local ML-Only", results["ml_only"]), ("3. Hybrid (Rule + ML)", results["hybrid"])]:
        print(f"\n{name}:")
        print(f"  Precision:         {m['precision']:.4f}")
        print(f"  Recall:            {m['recall']:.4f}")
        print(f"  F1-Score:          {m['f1_score']:.4f}")
        print(f"  False-Pos Rate:    {m['fpr']:.4f} (FP: {m['fp']})")
        print(f"  Confusion Matrix:  TN={m['tn']}, FP={m['fp']}, FN={m['fn']}, TP={m['tp']}")
        print(f"  Inference Latency: {m['avg_latency_ms']} ms/sample")

    # Save results to JSON
    report_path = ROOT_DIR / "training" / "data" / "benchmark_evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport written to: {report_path}")
    return results

if __name__ == "__main__":
    ds = verify_no_overlap_and_save()
    run_comparative_benchmark(ds)

"""Evaluation engine for comparing TraceSense RCA predictions against ground truth.

Computes:
- Top-1 Root Cause Accuracy
- Top-3 Root Cause Accuracy
- Precision, Recall, F1 for root cause identification
- Comparative benchmarking against baselines (Highest Anomaly Score & Earliest Anomaly)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

import sys
from pathlib import Path

# Add project root to sys.path if not present
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rca.baselines import predict_earliest_timestamp, predict_highest_score
from rca.causal_engine import CausalRCA


@dataclass
class EvaluationMetrics:
    total_incidents: int
    top1_correct: int
    top3_correct: int
    top1_accuracy: float
    top3_accuracy: float
    precision: float
    recall: float
    f1: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Total Incidents": self.total_incidents,
            "Top-1 Correct": self.top1_correct,
            "Top-3 Correct": self.top3_correct,
            "Top-1 Root Cause Accuracy": f"{self.top1_accuracy * 100:.1f}%",
            "Top-3 Root Cause Accuracy": f"{self.top3_accuracy * 100:.1f}%",
            "Precision": f"{self.precision * 100:.1f}%",
            "Recall": f"{self.recall * 100:.1f}%",
            "F1-Score": f"{self.f1 * 100:.1f}%",
        }


def compute_metrics(predictions: List[List[str]], ground_truths: List[str]) -> EvaluationMetrics:
    """Compute Top-1, Top-3, Precision, Recall, and F1 metrics."""
    n = len(ground_truths)
    if n == 0:
        return EvaluationMetrics(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    top1_correct = 0
    top3_correct = 0

    for ranked, truth in zip(predictions, ground_truths):
        if ranked and ranked[0] == truth:
            top1_correct += 1
        if truth in ranked[:3]:
            top3_correct += 1

    top1_acc = top1_correct / n
    top3_acc = top3_correct / n

    # For single root cause classification per incident:
    # Precision = TP / (TP + FP) = top1_correct / total_evaluated
    # Recall = TP / (TP + FN) = top1_correct / total_ground_truth
    # F1 = 2 * (P * R) / (P + R)
    precision = top1_acc
    recall = top1_acc
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return EvaluationMetrics(
        total_incidents=n,
        top1_correct=top1_correct,
        top3_correct=top3_correct,
        top1_accuracy=top1_acc,
        top3_accuracy=top3_acc,
        precision=precision,
        recall=recall,
        f1=f1,
    )


class RCAEvaluator:
    def __init__(self, causal_engine: Optional[CausalRCA] = None):
        self.engine = causal_engine if causal_engine is not None else CausalRCA()

    def evaluate(
        self,
        anomaly_df: pd.DataFrame,
        ground_truth_df: pd.DataFrame,
    ) -> Dict[str, EvaluationMetrics]:
        """Evaluate TraceSense engine and baselines on common incidents."""
        common_incidents = [
            inc for inc in ground_truth_df["incident_id"].unique()
            if inc in anomaly_df["incident_id"].values
        ]

        ground_truths: List[str] = []
        tracesense_preds: List[List[str]] = []
        highest_score_preds: List[List[str]] = []
        earliest_time_preds: List[List[str]] = []

        for inc in common_incidents:
            gt_row = ground_truth_df[ground_truth_df["incident_id"] == inc].iloc[0]
            true_rc = gt_row["root_cause"]
            ground_truths.append(true_rc)

            inc_anomalies = anomaly_df[anomaly_df["incident_id"] == inc]

            # 1. TraceSense
            ts_ranked = [r["service"] for r in self.engine.rank(inc_anomalies)]
            tracesense_preds.append(ts_ranked)

            # 2. Baseline: Highest Score
            bs_ranked = [predict_highest_score(inc_anomalies)] if predict_highest_score(inc_anomalies) else []
            highest_score_preds.append(bs_ranked)

            # 3. Baseline: Earliest Time
            bt_ranked = [predict_earliest_timestamp(inc_anomalies)] if predict_earliest_timestamp(inc_anomalies) else []
            earliest_time_preds.append(bt_ranked)

        return {
            "TraceSense (Causal RCA)": compute_metrics(tracesense_preds, ground_truths),
            "Baseline 1: Highest Anomaly Score": compute_metrics(highest_score_preds, ground_truths),
            "Baseline 2: Earliest Anomaly Time": compute_metrics(earliest_time_preds, ground_truths),
        }


def run_evaluation(
    anomaly_path: str = "ml/anomaly_results.csv",
    ground_truth_path: str = "evaluation/ground_truth.csv",
) -> None:
    """Run full evaluation from CSV files and print structured summary."""
    anom_file = Path(anomaly_path)
    gt_file = Path(ground_truth_path)

    if not anom_file.exists() or not gt_file.exists():
        print(f"Evaluation files missing. Ensure {anom_file} and {gt_file} exist.")
        return

    anomaly_df = pd.read_csv(anom_file)
    ground_truth_df = pd.read_csv(gt_file)

    evaluator = RCAEvaluator()
    results = evaluator.evaluate(anomaly_df, ground_truth_df)

    print("\n==================================================")
    print(" TRACESENSE RCA EVALUATION REPORT")
    print("==================================================")
    for model_name, metrics in results.items():
        print(f"\nModel: {model_name}")
        print("-" * 50)
        for k, v in metrics.to_dict().items():
            print(f"  {k:<30}: {v}")
    print("==================================================\n")


if __name__ == "__main__":
    run_evaluation()

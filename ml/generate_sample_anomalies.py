"""Deterministic generator for synthetic anomaly results and ground truth for testing RCA.

NOTE: This CSV is a synthetic/test dataset for developing and verifying the TraceSense
RCA engine. It does not come from a live ML anomaly detection pipeline.
"""

from pathlib import Path
import pandas as pd

ML_DIR = Path(__file__).resolve().parent
ROOT_DIR = ML_DIR.parent
EVAL_DIR = ROOT_DIR / "evaluation"

SAMPLE_ANOMALIES = [
    # INC001: Classic cascading silent calculation fault starting at pricing-service
    {"incident_id": "INC001", "service": "pricing-service", "timestamp": "2026-09-21T20:02:15", "anomaly_score": 0.91, "metric": "latency"},
    {"incident_id": "INC001", "service": "promotion-service", "timestamp": "2026-09-21T20:02:16", "anomaly_score": 0.73, "metric": "latency"},
    {"incident_id": "INC001", "service": "tax-service", "timestamp": "2026-09-21T20:02:17", "anomaly_score": 0.68, "metric": "latency"},
    {"incident_id": "INC001", "service": "receipt-service", "timestamp": "2026-09-21T20:02:18", "anomaly_score": 0.95, "metric": "error_rate"},

    # INC002: Downstream fault originating at tax-service
    {"incident_id": "INC002", "service": "tax-service", "timestamp": "2026-09-21T20:05:31", "anomaly_score": 0.88, "metric": "latency"},
    {"incident_id": "INC002", "service": "receipt-service", "timestamp": "2026-09-21T20:05:32", "anomaly_score": 0.70, "metric": "latency"},

    # INC003: Isolated anomaly in inventory-service
    {"incident_id": "INC003", "service": "inventory-service", "timestamp": "2026-09-21T20:10:00", "anomaly_score": 0.85, "metric": "error_rate"},
]

GROUND_TRUTH = [
    {"incident_id": "INC001", "root_cause": "pricing-service", "fault_type": "logic", "fault_timestamp": "2026-09-21T20:02:15"},
    {"incident_id": "INC002", "root_cause": "tax-service", "fault_type": "latency", "fault_timestamp": "2026-09-21T20:05:31"},
    {"incident_id": "INC003", "root_cause": "inventory-service", "fault_type": "error", "fault_timestamp": "2026-09-21T20:10:00"},
]


def generate():
    ML_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    df_anomalies = pd.DataFrame(SAMPLE_ANOMALIES)
    anomaly_csv = ML_DIR / "anomaly_results.csv"
    df_anomalies.to_csv(anomaly_csv, index=False)
    print(f"Generated {len(df_anomalies)} anomaly records at {anomaly_csv}")

    df_truth = pd.DataFrame(GROUND_TRUTH)
    truth_csv = EVAL_DIR / "ground_truth.csv"
    df_truth.to_csv(truth_csv, index=False)
    print(f"Generated {len(df_truth)} ground truth records at {truth_csv}")


if __name__ == "__main__":
    generate()

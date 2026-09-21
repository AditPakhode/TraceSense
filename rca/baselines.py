"""Baseline RCA methods for comparison with TraceSense causal ranking.

Baseline 1: Highest Anomaly Score (argmax(anomaly_score))
Baseline 2: Earliest Anomaly (argmin(timestamp))
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rca.causal_engine import parse_timestamp


def _to_records(anomalies: Union[List[Dict[str, Any]], pd.DataFrame], incident_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if isinstance(anomalies, pd.DataFrame):
        df = anomalies.copy()
        if incident_id and "incident_id" in df.columns:
            df = df[df["incident_id"] == incident_id]
        return df.to_dict(orient="records")
    if isinstance(anomalies, list):
        if incident_id:
            return [r for r in anomalies if r.get("incident_id") == incident_id]
        return anomalies
    return []


def rank_by_highest_score(
    anomalies: Union[List[Dict[str, Any]], pd.DataFrame], incident_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Rank services purely by highest anomaly score."""
    records = _to_records(anomalies, incident_id)
    if not records:
        return []

    # Aggregate max score per service
    svc_scores: Dict[str, float] = {}
    for r in records:
        svc = r.get("service")
        score = float(r.get("anomaly_score", 0.0))
        if svc not in svc_scores or score > svc_scores[svc]:
            svc_scores[svc] = score

    sorted_svcs = sorted(svc_scores.items(), key=lambda x: (-x[1], x[0]))
    return [{"rank": i, "service": s, "anomaly_score": sc} for i, (s, sc) in enumerate(sorted_svcs, start=1)]


def rank_by_earliest_timestamp(
    anomalies: Union[List[Dict[str, Any]], pd.DataFrame], incident_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Rank services purely by earliest anomaly timestamp."""
    records = _to_records(anomalies, incident_id)
    if not records:
        return []

    # Aggregate earliest timestamp per service
    svc_times: Dict[str, Any] = {}
    for r in records:
        svc = r.get("service")
        dt = parse_timestamp(r.get("timestamp"))
        if svc not in svc_times or dt < svc_times[svc]:
            svc_times[svc] = dt

    sorted_svcs = sorted(svc_times.items(), key=lambda x: (x[1], x[0]))
    return [{"rank": i, "service": s, "timestamp": str(dt)} for i, (s, dt) in enumerate(sorted_svcs, start=1)]


def predict_highest_score(anomalies: Union[List[Dict[str, Any]], pd.DataFrame], incident_id: Optional[str] = None) -> Optional[str]:
    ranked = rank_by_highest_score(anomalies, incident_id)
    return ranked[0]["service"] if ranked else None


def predict_earliest_timestamp(anomalies: Union[List[Dict[str, Any]], pd.DataFrame], incident_id: Optional[str] = None) -> Optional[str]:
    ranked = rank_by_earliest_timestamp(anomalies, incident_id)
    return ranked[0]["service"] if ranked else None

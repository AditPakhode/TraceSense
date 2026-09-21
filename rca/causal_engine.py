"""TraceSense Causal Root Cause Analysis (RCA) Engine.

Combines:
1. Anomaly timing (temporal score via exponential decay)
2. Service dependency topology (upstream influence score)
3. Downstream anomaly coverage
4. Anomaly strength (validated anomaly score)

Calculates the RCA Score as a ranking score (NOT a probability/confidence percentage).
"""

from dataclasses import dataclass, field
import datetime
import math
from typing import Any, Dict, List, Optional, Set, Union
import networkx as nx
import pandas as pd

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rca.dependency_graph import (
    build_default_graph,
    get_descendants,
    get_downstream_anomalies,
)


@dataclass
class AnomalyRecord:
    """Standardized representation of a single service anomaly record."""
    service: str
    timestamp: datetime.datetime
    anomaly_score: float
    metric: str = "general"
    incident_id: Optional[str] = None
    raw_timestamp: str = ""


@dataclass
class RCAScoreResult:
    """Detailed score breakdown for a candidate root cause."""
    service: str
    rank: int
    rca_score: float
    temporal_score: float
    topology_score: float
    coverage_score: float
    anomaly_score: float
    timestamp: str
    metric: str
    downstream_anomalies: List[str] = field(default_factory=list)
    in_graph: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "rank": self.rank,
            "rca_score": round(self.rca_score, 4),
            "temporal_score": round(self.temporal_score, 4),
            "topology_score": round(self.topology_score, 4),
            "coverage_score": round(self.coverage_score, 4),
            "anomaly_score": round(self.anomaly_score, 4),
            "timestamp": self.timestamp,
            "metric": self.metric,
            "downstream_anomalies": self.downstream_anomalies,
            "in_graph": self.in_graph,
        }


def parse_timestamp(val: Any) -> datetime.datetime:
    """Parse string or datetime object into timezone-aware or consistent UTC datetime.
    
    Raises ValueError with a clear validation message if malformed.
    """
    if val is None or (isinstance(val, float) and math.isnan(val)):
        raise ValueError("Missing or NaN timestamp provided")
    if isinstance(val, datetime.datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=datetime.timezone.utc)
        return val
    if isinstance(val, str):
        val_clean = val.strip()
        if not val_clean:
            raise ValueError("Empty timestamp string provided")
        # Handle ISO formats and common date formats
        try:
            # Replace Z with UTC offset if needed
            ts_str = val_clean.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except Exception as exc:
            raise ValueError(f"Malformed timestamp '{val}': cannot parse as ISO datetime") from exc
    raise ValueError(f"Malformed timestamp of type {type(val).__name__}: {val}")


class CausalRCA:
    """Causal Root Cause Analysis Engine for distributed microservices."""

    DEFAULT_WEIGHTS = {
        "temporal": 0.35,
        "topology": 0.30,
        "coverage": 0.20,
        "anomaly_strength": 0.15,
    }

    def __init__(
        self,
        graph: Optional[nx.DiGraph] = None,
        weights: Optional[Dict[str, float]] = None,
        time_decay_lambda: float = 0.1,
    ):
        """Initialize CausalRCA with a dependency graph and configurable weights.
        
        Args:
            graph: NetworkX DiGraph where edge A -> B means A calls B.
                   Defaults to the TraceSense default microservice graph.
            weights: Dictionary containing weights for 'temporal', 'topology', 'coverage', 'anomaly_strength'.
            time_decay_lambda: Exponential decay coefficient for temporal scoring.
        """
        self.graph = graph if graph is not None else build_default_graph()
        self.weights = dict(self.DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)

        # Validate weights sum to ~1.0
        total_w = sum(self.weights.values())
        if abs(total_w - 1.0) > 1e-4:
            # Normalize weights if user provided non-normalized values
            self.weights = {k: v / total_w for k, v in self.weights.items()}

        self.time_decay_lambda = time_decay_lambda

    def _normalize_input(
        self, anomalies: Union[List[Dict[str, Any]], pd.DataFrame], incident_id: Optional[str] = None
    ) -> List[AnomalyRecord]:
        """Convert list of dicts or pandas DataFrame into validated AnomalyRecord list."""
        if isinstance(anomalies, pd.DataFrame):
            records_df = anomalies.copy()
            if incident_id and "incident_id" in records_df.columns:
                records_df = records_df[records_df["incident_id"] == incident_id]
            raw_records = records_df.to_dict(orient="records")
        elif isinstance(anomalies, list):
            if incident_id:
                raw_records = [r for r in anomalies if r.get("incident_id") == incident_id]
            else:
                raw_records = anomalies
        else:
            raise TypeError(f"Expected list of dicts or pd.DataFrame, got {type(anomalies).__name__}")

        parsed_records: List[AnomalyRecord] = []
        for row in raw_records:
            service = str(row.get("service", "")).strip()
            if not service:
                continue

            raw_ts = row.get("timestamp")
            parsed_dt = parse_timestamp(raw_ts)

            # Validate anomaly_score
            raw_score = row.get("anomaly_score")
            try:
                score_val = float(raw_score)
            except (TypeError, ValueError) as e:
                raise ValueError(f"Invalid anomaly_score '{raw_score}' for service {service}: must be numeric") from e

            if score_val < 0.0 or score_val > 1.0:
                raise ValueError(f"Invalid anomaly_score {score_val} for service {service}: must be in range [0, 1]")

            parsed_records.append(
                AnomalyRecord(
                    service=service,
                    timestamp=parsed_dt,
                    anomaly_score=score_val,
                    metric=str(row.get("metric", "unknown")),
                    incident_id=str(row.get("incident_id", "")) if row.get("incident_id") else None,
                    raw_timestamp=str(raw_ts),
                )
            )

        return parsed_records

    def rank(
        self, anomalies: Union[List[Dict[str, Any]], pd.DataFrame], incident_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Rank candidate services by calculated RCA Score.

        Returns clean empty list if no anomalies are provided.
        """
        records = self._normalize_input(anomalies, incident_id=incident_id)
        if not records:
            return []

        # If a service has multiple anomaly events in the same incident, aggregate:
        # earliest timestamp, maximum anomaly score
        service_map: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            svc = rec.service
            if svc not in service_map:
                service_map[svc] = {
                    "service": svc,
                    "earliest_ts": rec.timestamp,
                    "max_score": rec.anomaly_score,
                    "metric": rec.metric,
                    "raw_timestamp": rec.raw_timestamp,
                }
            else:
                if rec.timestamp < service_map[svc]["earliest_ts"]:
                    service_map[svc]["earliest_ts"] = rec.timestamp
                    service_map[svc]["raw_timestamp"] = rec.raw_timestamp
                if rec.anomaly_score > service_map[svc]["max_score"]:
                    service_map[svc]["max_score"] = rec.anomaly_score
                    service_map[svc]["metric"] = rec.metric

        unique_services = list(service_map.keys())
        total_anomalous_services = len(unique_services)
        all_anomalous_set = set(unique_services)

        # 1. Earliest global timestamp across all anomalies in this incident
        earliest_global_ts = min(s["earliest_ts"] for s in service_map.values())

        scored_candidates: List[RCAScoreResult] = []

        for svc, sdata in service_map.items():
            in_graph = svc in self.graph

            # -------------------------------------------------------------
            # Temporal Score: T(s) = exp(-lambda * delta_seconds)
            # -------------------------------------------------------------
            delta_seconds = (sdata["earliest_ts"] - earliest_global_ts).total_seconds()
            if delta_seconds < 0:
                delta_seconds = 0.0
            temporal_score = math.exp(-self.time_decay_lambda * delta_seconds)

            # -------------------------------------------------------------
            # Topology Score & Downstream Coverage
            # -------------------------------------------------------------
            if in_graph:
                downstream_anomalies = sorted(
                    list(get_downstream_anomalies(self.graph, svc, all_anomalous_set - {svc}))
                )
            else:
                downstream_anomalies = []

            num_downstream = len(downstream_anomalies)

            # Topology Score: normalized by max possible other anomalous services (total - 1)
            # If total_anomalous_services == 1, there are no other anomalous services, topology_score = 0.0
            if total_anomalous_services > 1:
                topology_score = num_downstream / (total_anomalous_services - 1)
            else:
                topology_score = 0.0

            # Downstream Coverage:
            # coverage = (number of anomalous descendants explained by S) / (total number of anomalous services)
            coverage_score = num_downstream / total_anomalous_services

            # Anomaly Strength Score:
            strength_score = sdata["max_score"]

            # Final RCA Score:
            # 0.35 * temporal + 0.30 * topology + 0.20 * coverage + 0.15 * anomaly_score
            rca_score = (
                self.weights["temporal"] * temporal_score
                + self.weights["topology"] * topology_score
                + self.weights["coverage"] * coverage_score
                + self.weights["anomaly_strength"] * strength_score
            )

            scored_candidates.append(
                RCAScoreResult(
                    service=svc,
                    rank=0,  # assigned after sorting
                    rca_score=rca_score,
                    temporal_score=temporal_score,
                    topology_score=topology_score,
                    coverage_score=coverage_score,
                    anomaly_score=strength_score,
                    timestamp=sdata["raw_timestamp"],
                    metric=sdata["metric"],
                    downstream_anomalies=downstream_anomalies,
                    in_graph=in_graph,
                )
            )

        # Deterministic sorting:
        # Primary: rca_score descending
        # Secondary: temporal_score descending
        # Tertiary: topology_score descending
        # Quaternary: service name ascending
        scored_candidates.sort(
            key=lambda c: (-c.rca_score, -c.temporal_score, -c.topology_score, c.service)
        )

        # Assign ranks
        results: List[Dict[str, Any]] = []
        for i, candidate in enumerate(scored_candidates, start=1):
            candidate.rank = i
            results.append(candidate.to_dict())

        return results

    def explain(self, ranked_results: List[Dict[str, Any]]) -> str:
        """Generate human-readable explanation for ranked results."""
        from rca.explanation import explain_results
        return explain_results(self.graph, ranked_results)

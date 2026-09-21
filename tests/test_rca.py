"""Comprehensive Unit Tests for TraceSense RCA Engine.

Validates:
TEST 1: pricing-service is earliest and upstream of all anomalies -> ranked #1.
TEST 2: receipt-service has highest anomaly score but is downstream -> TraceSense ranks pricing-service above receipt-service.
TEST 3: Two unrelated branches have anomalies -> algorithm does not assume everything belongs to one causal chain.
TEST 4: Two services have identical timestamps -> no crash and deterministic ranking.
TEST 5: Single anomalous service -> that service is returned as the candidate.
TEST 6: No anomalies -> clean empty result, not an exception.
TEST 7: Malformed timestamp -> clear validation error.
TEST 8: Unknown service not present in graph -> handle gracefully and explain missing topology information.
Plus Dependency Graph & Evaluation tests.
"""

import datetime
import pytest
import networkx as nx

from rca.causal_engine import CausalRCA
from rca.dependency_graph import (
    build_default_graph,
    get_ancestors,
    get_descendants,
    get_downstream_anomalies,
    has_path,
)
from rca.baselines import (
    predict_earliest_timestamp,
    predict_highest_score,
    rank_by_earliest_timestamp,
    rank_by_highest_score,
)
from rca.evaluation import compute_metrics, RCAEvaluator
from rca.explanation import explain_results


@pytest.fixture
def default_graph():
    return build_default_graph()


@pytest.fixture
def rca_engine(default_graph):
    return CausalRCA(graph=default_graph)


# =====================================================================
# Graph Query Tests
# =====================================================================

def test_graph_ancestors_and_descendants(default_graph):
    pricing_ancestors = get_ancestors(default_graph, "pricing-service")
    assert pricing_ancestors == {"checkout-api", "cart-service", "inventory-service"}

    pricing_descendants = get_descendants(default_graph, "pricing-service")
    assert pricing_descendants == {"promotion-service", "tax-service", "receipt-service"}

    assert has_path(default_graph, "checkout-api", "receipt-service")
    assert not has_path(default_graph, "receipt-service", "checkout-api")

    downstream = get_downstream_anomalies(
        default_graph,
        "pricing-service",
        ["promotion-service", "receipt-service", "cart-service"],
    )
    assert downstream == {"promotion-service", "receipt-service"}


# =====================================================================
# Required Core RCA Tests
# =====================================================================

def test_1_pricing_service_earliest_and_upstream(rca_engine):
    """TEST 1: pricing-service is earliest and upstream of all anomalies -> ranked #1."""
    anomalies = [
        {"service": "pricing-service", "timestamp": "2026-09-21T20:00:00Z", "anomaly_score": 0.85},
        {"service": "promotion-service", "timestamp": "2026-09-21T20:00:02Z", "anomaly_score": 0.80},
        {"service": "tax-service", "timestamp": "2026-09-21T20:00:04Z", "anomaly_score": 0.75},
        {"service": "receipt-service", "timestamp": "2026-09-21T20:00:06Z", "anomaly_score": 0.70},
    ]
    ranked = rca_engine.rank(anomalies)
    assert len(ranked) == 4
    assert ranked[0]["service"] == "pricing-service"
    assert ranked[0]["rank"] == 1
    assert ranked[0]["topology_score"] == 1.0
    assert ranked[0]["temporal_score"] == 1.0


def test_2_downstream_highest_anomaly_score(rca_engine):
    """TEST 2: receipt-service has highest anomaly score (0.99) but is downstream.
    TraceSense can rank pricing-service above receipt-service when topology/timing evidence supports it.
    """
    anomalies = [
        {"service": "pricing-service", "timestamp": "2026-09-21T20:02:15Z", "anomaly_score": 0.70},
        {"service": "promotion-service", "timestamp": "2026-09-21T20:02:16Z", "anomaly_score": 0.75},
        {"service": "tax-service", "timestamp": "2026-09-21T20:02:17Z", "anomaly_score": 0.80},
        {"service": "receipt-service", "timestamp": "2026-09-21T20:02:18Z", "anomaly_score": 0.99},
    ]
    # Baseline 1 would incorrectly pick receipt-service
    assert predict_highest_score(anomalies) == "receipt-service"

    # TraceSense correctly ranks pricing-service higher due to temporal + topology evidence
    ranked = rca_engine.rank(anomalies)
    assert ranked[0]["service"] == "pricing-service"
    # Find rank of receipt-service
    receipt_entry = next(r for r in ranked if r["service"] == "receipt-service")
    assert ranked[0]["rca_score"] > receipt_entry["rca_score"]


def test_3_two_unrelated_branches():
    """TEST 3: Two unrelated branches have anomalies.
    Algorithm does not incorrectly assume everything belongs to one causal chain.
    """
    # Create a branching DAG:
    # gateway -> serviceA -> serviceA_leaf
    # gateway -> serviceB -> serviceB_leaf
    branching_graph = nx.DiGraph()
    branching_graph.add_edges_from([
        ("gateway", "serviceA"),
        ("serviceA", "serviceA_leaf"),
        ("gateway", "serviceB"),
        ("serviceB", "serviceB_leaf"),
    ])

    engine = CausalRCA(graph=branching_graph)

    anomalies = [
        {"service": "serviceA", "timestamp": "2026-09-21T20:00:01Z", "anomaly_score": 0.85},
        {"service": "serviceA_leaf", "timestamp": "2026-09-21T20:00:03Z", "anomaly_score": 0.80},
        {"service": "serviceB", "timestamp": "2026-09-21T20:00:00Z", "anomaly_score": 0.85},
        {"service": "serviceB_leaf", "timestamp": "2026-09-21T20:00:02Z", "anomaly_score": 0.80},
    ]

    ranked = engine.rank(anomalies)
    svc_a = next(r for r in ranked if r["service"] == "serviceA")
    svc_b = next(r for r in ranked if r["service"] == "serviceB")

    # Downstream anomalies of serviceA should ONLY be serviceA_leaf (not serviceB or serviceB_leaf)
    assert svc_a["downstream_anomalies"] == ["serviceA_leaf"]
    assert svc_b["downstream_anomalies"] == ["serviceB_leaf"]

    # Neither service should have full coverage of the other branch's anomalies
    assert svc_a["coverage_score"] == 1 / 4
    assert svc_b["coverage_score"] == 1 / 4


def test_4_identical_timestamps(rca_engine):
    """TEST 4: Two services have identical timestamps -> no crash and deterministic ranking."""
    anomalies = [
        {"service": "tax-service", "timestamp": "2026-09-21T20:00:00Z", "anomaly_score": 0.80},
        {"service": "pricing-service", "timestamp": "2026-09-21T20:00:00Z", "anomaly_score": 0.80},
    ]
    ranked1 = rca_engine.rank(anomalies)
    ranked2 = rca_engine.rank(anomalies)

    # Deterministic output
    assert [r["service"] for r in ranked1] == [r["service"] for r in ranked2]
    # Both have delta_seconds = 0 -> temporal_score = 1.0
    assert ranked1[0]["temporal_score"] == 1.0
    assert ranked1[1]["temporal_score"] == 1.0
    # pricing-service is upstream of tax-service, so pricing-service should win on topology
    assert ranked1[0]["service"] == "pricing-service"


def test_5_single_anomalous_service(rca_engine):
    """TEST 5: Single anomalous service -> that service is returned as the candidate."""
    anomalies = [
        {"service": "inventory-service", "timestamp": "2026-09-21T20:10:00Z", "anomaly_score": 0.90}
    ]
    ranked = rca_engine.rank(anomalies)
    assert len(ranked) == 1
    assert ranked[0]["service"] == "inventory-service"
    assert ranked[0]["rank"] == 1
    assert ranked[0]["temporal_score"] == 1.0
    assert ranked[0]["topology_score"] == 0.0
    assert ranked[0]["coverage_score"] == 0.0


def test_6_no_anomalies(rca_engine):
    """TEST 6: No anomalies -> clean empty result, not an exception."""
    ranked = rca_engine.rank([])
    assert ranked == []

    explanation = rca_engine.explain([])
    assert "No anomalies detected" in explanation


def test_7_malformed_timestamp(rca_engine):
    """TEST 7: Malformed timestamp -> clear validation error."""
    anomalies = [
        {"service": "pricing-service", "timestamp": "not-a-valid-date-string", "anomaly_score": 0.8}
    ]
    with pytest.raises(ValueError, match="Malformed timestamp"):
        rca_engine.rank(anomalies)


def test_8_unknown_service_not_in_graph(rca_engine, default_graph):
    """TEST 8: Unknown service not present in graph -> handle gracefully and explain missing topology."""
    anomalies = [
        {"service": "external-payment-gateway", "timestamp": "2026-09-21T20:00:00Z", "anomaly_score": 0.95},
        {"service": "receipt-service", "timestamp": "2026-09-21T20:00:05Z", "anomaly_score": 0.70},
    ]
    ranked = rca_engine.rank(anomalies)
    assert len(ranked) == 2

    unknown_entry = next(r for r in ranked if r["service"] == "external-payment-gateway")
    assert unknown_entry["in_graph"] is False
    assert unknown_entry["topology_score"] == 0.0
    assert unknown_entry["downstream_anomalies"] == []

    # Check explanation handles missing topology
    explanation = explain_results(default_graph, ranked)
    assert "Service is not present in dependency graph" in explanation


# =====================================================================
# Additional Validation & Evaluation Tests
# =====================================================================

def test_anomaly_score_validation(rca_engine):
    """Ensure invalid anomaly score (>1 or <0) raises ValueError."""
    with pytest.raises(ValueError, match="Invalid anomaly_score"):
        rca_engine.rank([{"service": "cart-service", "timestamp": "2026-09-21T20:00:00Z", "anomaly_score": 1.5}])

    with pytest.raises(ValueError, match="Invalid anomaly_score"):
        rca_engine.rank([{"service": "cart-service", "timestamp": "2026-09-21T20:00:00Z", "anomaly_score": -0.1}])


def test_evaluation_metrics_computation():
    predictions = [
        ["pricing-service", "cart-service"],
        ["receipt-service", "tax-service"],
    ]
    ground_truth = ["pricing-service", "tax-service"]

    metrics = compute_metrics(predictions, ground_truth)
    assert metrics.total_incidents == 2
    assert metrics.top1_correct == 1
    assert metrics.top1_accuracy == 0.5
    assert metrics.top3_correct == 2
    assert metrics.top3_accuracy == 1.0

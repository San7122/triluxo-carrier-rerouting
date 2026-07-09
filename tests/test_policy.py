"""Tests for the policy oracle (agents/policy.py).

The oracle is the ground truth every decision is graded against, so its
correctness is load-bearing for the entire evaluation. These tests pin the
viability filter, the objective, and the tie-break order.
"""
from agents.policy import policy_optimal, viable_options

POLICY = {"max_cost_usd": 3000, "min_reliability": 0.9}


def _c(cid, cost, eta, rel):
    return {"carrier_id": cid, "cost_usd": cost, "eta_hours": eta, "reliability": rel}


def test_viable_filters_cost_and_reliability():
    carriers = [
        _c("A", 5000, 28, 0.97),   # cost too high
        _c("B", 1500, 70, 0.72),   # reliability too low
        _c("C", 2000, 40, 0.95),   # compliant
    ]
    viable = viable_options(carriers, POLICY)
    assert [o["carrier_id"] for o in viable] == ["C"]


def test_optimal_minimises_eta_among_viable():
    carriers = [
        _c("SLOW", 1000, 60, 0.99),
        _c("FAST", 2500, 20, 0.91),
        _c("MID", 1500, 40, 0.95),
    ]
    assert policy_optimal(carriers, POLICY)["carrier_id"] == "FAST"


def test_optimal_tiebreak_prefers_higher_reliability_then_lower_cost():
    # Same ETA -> higher reliability wins
    carriers = [
        _c("LOWREL", 1000, 30, 0.91),
        _c("HIGHREL", 2000, 30, 0.98),
    ]
    assert policy_optimal(carriers, POLICY)["carrier_id"] == "HIGHREL"
    # Same ETA and reliability -> lower cost wins
    carriers2 = [
        _c("PRICEY", 2500, 30, 0.95),
        _c("CHEAP", 1200, 30, 0.95),
    ]
    assert policy_optimal(carriers2, POLICY)["carrier_id"] == "CHEAP"


def test_no_viable_option_returns_none():
    carriers = [
        _c("A", 5000, 28, 0.97),   # cost too high
        _c("B", 1500, 70, 0.72),   # reliability too low
        _c("C", 3200, 50, 0.85),   # both fail (the real no_viable_option case)
    ]
    assert policy_optimal(carriers, POLICY) is None

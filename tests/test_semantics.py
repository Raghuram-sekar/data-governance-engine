import pytest
from semantics.engine import semantic_engine
from semantics.models import SensitivityLevel


def test_glossary_term_lookup():
    term = semantic_engine.lookup_glossary_term("user_email")
    assert term is not None
    assert term.name == "Customer Email Address"
    assert term.sensitivity == SensitivityLevel.PII


def test_sensitivity_matching_pii_email():
    match = semantic_engine.match_sensitivity("user_email", "VARCHAR")
    assert match is not None
    rule, conf = match
    assert rule.classification == SensitivityLevel.PII
    assert conf >= 0.90


def test_sensitivity_matching_pci_card():
    match = semantic_engine.match_sensitivity("raw_credit_card", "VARCHAR")
    assert match is not None
    rule, conf = match
    assert rule.classification == SensitivityLevel.PCI
    assert conf >= 0.95


def test_metric_health_and_drift_detection():
    from semantics.engine import SemanticEngine
    engine = SemanticEngine()
    
    # When columns are intact
    healthy_cols = ["order_total", "is_recurring"]
    res = engine.check_metric_health("annual_recurring_revenue", healthy_cols)
    assert res["is_healthy"] is True

    # When order_total was renamed to gross_rev (drift)
    drifted_cols = ["gross_rev", "is_recurring"]
    res_drift = engine.check_metric_health("annual_recurring_revenue", drifted_cols)
    assert res_drift["is_healthy"] is False
    assert "order_total" in res_drift["missing_columns"]
    assert res_drift["suggested_mappings"].get("order_total") == "gross_rev"


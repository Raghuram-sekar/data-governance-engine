import pytest
from connectors import connector_registry
from engine.yaml_runner import YAMLGovernanceRunner


def test_connector_registry():
    connectors = connector_registry.list_all()
    assert "atlan" in connectors
    assert "postgres" in connectors
    assert "mongodb" in connectors
    assert "chroma" in connectors

    for conn_id, conn in connectors.items():
        assert conn.connect() is True
        tables = conn.list_tables()
        assert len(tables) > 0


def test_yaml_governance_runner():
    runner = YAMLGovernanceRunner()
    results = runner.execute_all_checkpoints()

    assert len(results["connected_sources"]) == 4
    assert len(results["privacy_evaluations"]) > 0
    assert results["total_anomalies_healed"] >= 0

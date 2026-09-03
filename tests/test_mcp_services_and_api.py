import pytest
from fastapi.testclient import TestClient
from server import app
from services.mcp_registry import mcp_registry
from atlan_integration.client import atlan_client


@pytest.fixture
def client():
    atlan_client.reset()
    return TestClient(app)


def test_mcp_registry_discovery():
    services = mcp_registry.discover_services()
    service_names = [s.service_name for s in services]

    assert "mcp-pii-selfhealerservice" in service_names
    assert "mcp-metadata-selfhealerservice" in service_names
    assert "mcp-drift-selfhealerservice" in service_names

    # Check tools exposed
    pii_svc = mcp_registry.get_service("mcp-pii-selfhealerservice")
    assert pii_svc is not None
    tool_names = [t.name for t in pii_svc.list_tools()]
    assert "evaluate_sensitivity" in tool_names
    assert "enforce_database_masking" in tool_names


def test_mcp_pii_service_tool_call():
    pii_svc = mcp_registry.get_service("mcp-pii-selfhealerservice")
    res = pii_svc.call_tool("evaluate_sensitivity", {"column_name": "user_email", "data_type": "VARCHAR"})
    assert res.status == "SUCCESS"
    assert res.result["is_sensitive"] is True
    assert res.result["classification"] == "PII"


def test_mcp_metadata_service_tool_call():
    meta_svc = mcp_registry.get_service("mcp-metadata-selfhealerservice")
    res = meta_svc.call_tool("lookup_glossary_definition", {"term_query": "user_email"})
    assert res.status == "SUCCESS"
    assert res.result["found"] is True
    assert res.result["name"] == "Customer Email Address"


def test_mcp_drift_service_tool_call():
    atlan_client.reset()
    drift_svc = mcp_registry.get_service("mcp-drift-selfhealerservice")
    res = drift_svc.call_tool("validate_metric_health", {
        "metric_name": "annual_recurring_revenue",
        "table_columns": ["gross_rev", "is_recurring"]
    })
    assert res.status == "SUCCESS"
    assert res.result["is_healthy"] is False
    assert "order_total" in res.result["missing_columns"]


def test_api_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
    assert "governance_scores" in data
    assert "registered_mcp_services" in data


def test_api_mcp_services_discovery(client):
    response = client.get("/api/v1/mcp/services")
    assert response.status_code == 200
    services = response.json()
    assert len(services) >= 3


def test_api_key_orchestrator_pii_routing(client):
    payload = {
        "anomaly_type": "UNCLASSIFIED_PII",
        "connector": "postgres",
        "table_name": "dim_customers",
        "column_name": "tax_ssn",
        "data_type": "VARCHAR"
    }
    response = client.post("/api/v1/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["discovered_mcp_service"] == "mcp-pii-selfhealerservice"
    assert data["selected_tool"] == "enforce_database_masking"
    assert data["remediation_result"]["masking_active"] is True


def test_api_key_orchestrator_metadata_routing(client):
    payload = {
        "anomaly_type": "MISSING_DESCRIPTION",
        "connector": "atlan",
        "table_name": "dim_customers",
        "column_name": "user_email",
        "asset_guid": "col-cust-002"
    }
    response = client.post("/api/v1/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["discovered_mcp_service"] == "mcp-metadata-selfhealerservice"
    assert data["selected_tool"] == "heal_column_metadata"


def test_api_key_orchestrator_drift_routing(client):
    payload = {
        "anomaly_type": "SEMANTIC_METRIC_DRIFT",
        "connector": "atlan",
        "table_name": "fct_orders",
        "metric_name": "annual_recurring_revenue",
        "raw_payload": {"columns": ["order_id", "gross_rev", "is_recurring"]}
    }
    response = client.post("/api/v1/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["discovered_mcp_service"] == "mcp-drift-selfhealerservice"
    assert data["selected_tool"] == "diagnose_and_heal_metric_drift"


def test_api_audit_trail_endpoint(client):
    response = client.get("/api/v1/audit")
    assert response.status_code == 200
    data = response.json()
    assert "total_events" in data
    assert "audit_trail" in data

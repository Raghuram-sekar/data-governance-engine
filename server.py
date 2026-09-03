import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services.mcp_registry import mcp_registry
from services.mcp_base import MCPCallRequest, MCPCallResponse, MCPServiceMetadata
from engine.loop import SelfHealingLoop
from engine.detector import GovernanceDetector
from atlan_integration.client import atlan_client
from connectors import connector_registry
from observability.phoenix_tracer import phoenix_tracer

app = FastAPI(
    title="Autonomous Data Governance & MCP Microservices Engine",
    description="Enterprise Multi-Database Self-Healing Platform powered by Agno, Atlan, FastMCP, and Arize Phoenix",
    version="2.0.0"
)

# Enable CORS for external dashboards and UI clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------
class OrchestrationEventRequest(BaseModel):
    anomaly_type: str = Field(
        ...,
        description="Type of governance anomaly (e.g. UNCLASSIFIED_PII, MISSING_DESCRIPTION, MISSING_OWNER, SEMANTIC_METRIC_DRIFT)"
    )
    connector: Optional[str] = Field(default="atlan", description="Connector identifier (atlan, postgres, mongodb, chroma)")
    table_name: Optional[str] = Field(default=None, description="Target table or collection name")
    column_name: Optional[str] = Field(default=None, description="Target column or field name")
    asset_guid: Optional[str] = Field(default=None, description="Atlan or Connector GUID")
    data_type: Optional[str] = Field(default="VARCHAR", description="Data type of field")
    metric_name: Optional[str] = Field(default=None, description="KPI identifier for drift diagnosis")
    raw_payload: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary webhook payload parameters")


class OrchestrationResponse(BaseModel):
    status: str
    anomaly_type: str
    discovered_mcp_service: str
    selected_tool: str
    remediation_result: Dict[str, Any]
    latency_ms: float
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------
# 1. Main Key-Orchestration Route (MCP Discovery & Routing)
# ---------------------------------------------------------
@app.post(
    "/api/v1/orchestrate",
    response_model=OrchestrationResponse,
    summary="Key Orchestrator Agent - Receives JSON, Discovers & Invokes MCP Services",
    tags=["Key Orchestrator Agent"]
)
async def orchestrate_governance_event(event: OrchestrationEventRequest):
    """
    Key-Orchestrator Agent Decorator & Dispatcher.
    1. Receives incoming JSON anomaly payload from webhooks, pipelines, or catalogs.
    2. Performs dynamic discovery across registered MCP self-healing microservices.
    3. Formats input JSON arguments and invokes the appropriate `-mcp-selfhealerservice`.
    4. Records OpenTelemetry trace to Arize Phoenix.
    """
    start_time = time.time()

    # Step 1: Dynamic Discovery of MCP Self-Healing Service
    target_service = mcp_registry.route_for_anomaly(event.anomaly_type)

    if not target_service:
        # Fallback to general lookup
        raise HTTPException(
            status_code=404,
            detail=f"No MCP Self-Healing service discovered for anomaly type '{event.anomaly_type}'. Registered services: {[s.service_name for s in mcp_registry.discover_services()]}"
        )

    service_name = target_service.metadata.service_name
    tool_to_call = ""
    tool_arguments: Dict[str, Any] = {}

    # Step 2: Formulate arguments based on discovered MCP service
    if service_name == "mcp-pii-selfhealerservice":
        conn_id = (event.connector or "atlan").lower()
        if conn_id != "atlan":
            tool_to_call = "enforce_database_masking"
            tool_arguments = {
                "connector_id": conn_id,
                "table_name": event.table_name or "dim_customers",
                "column_name": event.column_name or "tax_ssn"
            }
        else:
            tool_to_call = "heal_pii_column"
            tool_arguments = {
                "column_guid": event.asset_guid or f"col-{event.column_name}",
                "column_name": event.column_name or "user_email",
                "data_type": event.data_type or "VARCHAR"
            }

    elif service_name == "mcp-metadata-selfhealerservice":
        if event.column_name:
            tool_to_call = "heal_column_metadata"
            tool_arguments = {
                "column_guid": event.asset_guid or f"col-{event.column_name}",
                "column_name": event.column_name,
                "table_name": event.table_name or ""
            }
        else:
            tool_to_call = "heal_table_metadata"
            tool_arguments = {
                "table_guid": event.asset_guid or f"tbl-{event.table_name}",
                "table_name": event.table_name or "fct_orders",
                "schema_name": "public"
            }

    elif service_name == "mcp-drift-selfhealerservice":
        tool_to_call = "diagnose_and_heal_metric_drift"
        tool_arguments = {
            "metric_name": event.metric_name or "annual_recurring_revenue",
            "table_guid": event.asset_guid or "table-fct-orders-002",
            "table_columns": event.raw_payload.get("columns", ["order_id", "gross_rev", "is_recurring"])
        }

    # Step 3: Invoke the Discovered MCP Service
    mcp_res = target_service.call_tool(tool_to_call, tool_arguments)
    duration_ms = round((time.time() - start_time) * 1000, 2)

    # Step 4: Stream OpenTelemetry Trace to Arize Phoenix
    phoenix_tracer.log_agent_trace(
        agent_name=f"KeyOrchestrator -> {service_name}",
        task=f"Orchestrate resolution for '{event.anomaly_type}' via {tool_to_call}",
        input_data={
            "incoming_event": event.model_dump(),
            "discovered_service": service_name,
            "invoked_tool": tool_to_call,
            "tool_arguments": tool_arguments
        },
        output_data=mcp_res.result,
        tools_called=[tool_to_call],
        latency_ms=duration_ms
    )

    return OrchestrationResponse(
        status=mcp_res.status,
        anomaly_type=event.anomaly_type,
        discovered_mcp_service=service_name,
        selected_tool=tool_to_call,
        remediation_result=mcp_res.result,
        latency_ms=duration_ms
    )


# ---------------------------------------------------------
# 2. MCP Discovery & Tool Invocation Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/mcp/services", response_model=List[MCPServiceMetadata], tags=["MCP Discovery & Protocol"])
async def discover_mcp_services():
    """Returns the list of all registered MCP self-healing services and their exposed tool schemas."""
    return mcp_registry.discover_services()


@app.post("/api/v1/mcp/call", response_model=MCPCallResponse, tags=["MCP Discovery & Protocol"])
async def call_mcp_service_tool(service_name: str, request: MCPCallRequest):
    """Directly invokes an exposed tool on a specific MCP service."""
    res = mcp_registry.execute_tool(service_name, request.tool_name, request.arguments)
    return res


# ---------------------------------------------------------
# 3. Governance Lifecycle & Health Endpoints
# ---------------------------------------------------------
@app.get("/api/v1/health", tags=["Governance Operations"])
async def get_system_health():
    """Returns governance compliance scores and health across all 4 database connectors."""
    loop = SelfHealingLoop()
    return {
        "status": "ONLINE",
        "governance_scores": loop.calculate_health_score(),
        "registered_mcp_services": [s.service_name for s in mcp_registry.discover_services()],
        "connectors": list(connector_registry.list_all().keys()),
        "observability_dashboard": "http://localhost:6006"
    }


@app.post("/api/v1/scan", tags=["Governance Operations"])
async def scan_catalog():
    """Scans all multi-database assets and flags anomalies."""
    detector = GovernanceDetector()
    anomalies = detector.scan_catalog()
    return {
        "total_anomalies_detected": len(anomalies),
        "anomalies": [a.model_dump() for a in anomalies]
    }


@app.post("/api/v1/heal", tags=["Governance Operations"])
async def trigger_healing_cycle():
    """Executes the full end-to-end autonomous healing cycle across all databases."""
    loop = SelfHealingLoop()
    return loop.execute_healing_cycle()


@app.post("/api/v1/reset", tags=["Governance Operations"])
async def reset_catalog_state():
    """Resets catalog back to initial state with deliberate anomalies for fresh testing."""
    atlan_client.reset()
    return {"status": "SUCCESS", "message": "Catalog state reset successfully."}


@app.get("/api/v1/audit", tags=["Governance Operations"])
async def get_audit_trail():
    """Retrieves immutable Atlan governance audit logs."""
    trail = atlan_client.get_audit_trail()
    return {
        "total_events": len(trail),
        "audit_trail": [
            {
                "timestamp": r.timestamp.isoformat(),
                "action": r.action,
                "asset_name": r.asset_name,
                "actor": r.actor,
                "reason": r.reason
            }
            for r in trail
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

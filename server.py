import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse
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


@app.get("/", response_class=HTMLResponse, tags=["Visual Dashboard"])
async def visual_dashboard():
    """Renders the Interactive Self-Healing Governance Dashboard with live Phoenix observability."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Autonomous Data Governance & MCP Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
            body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #f3f4f6; }
            .glow-blue { box-shadow: 0 0 25px rgba(59, 130, 246, 0.2); }
            .glow-green { box-shadow: 0 0 25px rgba(16, 185, 129, 0.2); }
            .glow-purple { box-shadow: 0 0 25px rgba(168, 85, 247, 0.2); }
        </style>
    </head>
    <body class="min-h-screen flex flex-col p-6">
        <!-- Header -->
        <header class="max-w-7xl w-full mx-auto flex flex-col md:flex-row items-center justify-between gap-4 pb-6 border-b border-gray-800">
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white shadow-lg shadow-blue-500/30">
                    <i class="fa-solid fa-shield-halved text-2xl"></i>
                </div>
                <div>
                    <h1 class="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                        Autonomous Data Governance Engine
                        <span class="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-900/60 text-blue-300 border border-blue-700/50">v2.0 MCP</span>
                    </h1>
                    <p class="text-xs text-gray-400">Powered by Agno AI • Atlan Active Metadata • FastAPI • Arize Phoenix</p>
                </div>
            </div>

            <div class="flex items-center gap-3">
                <a href="http://localhost:6006" target="_blank" class="px-4 py-2 rounded-lg bg-orange-950/40 border border-orange-700/50 text-orange-300 hover:bg-orange-900/50 transition-all flex items-center gap-2 text-sm font-medium shadow-sm hover:shadow-orange-500/20">
                    <i class="fa-solid fa-fire text-orange-400"></i>
                    Arize Phoenix Traces
                    <i class="fa-solid fa-arrow-up-right-from-square text-xs opacity-70"></i>
                </a>
                <a href="/docs" target="_blank" class="px-4 py-2 rounded-lg bg-gray-800/80 border border-gray-700 text-gray-200 hover:bg-gray-700 transition-all flex items-center gap-2 text-sm font-medium">
                    <i class="fa-solid fa-code text-blue-400"></i>
                    Swagger API Docs
                </a>
            </div>
        </header>

        <!-- Main Content -->
        <main class="max-w-7xl w-full mx-auto py-8 space-y-8 flex-1">
            <!-- Controls & Action Banner -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <button onclick="triggerHeal()" id="btn-heal" class="md:col-span-2 p-5 rounded-2xl bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 text-white font-semibold text-lg hover:opacity-95 transition-all shadow-xl shadow-emerald-900/30 flex items-center justify-between group">
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center text-2xl group-hover:scale-110 transition-transform">
                            <i class="fa-solid fa-wand-magic-sparkles"></i>
                        </div>
                        <div class="text-left">
                            <div class="font-bold">Execute Autonomous Self-Healing</div>
                            <div class="text-xs text-emerald-100 font-normal">Dispatches MCP specialist agents to fix all gaps</div>
                        </div>
                    </div>
                    <i class="fa-solid fa-arrow-right text-emerald-200 group-hover:translate-x-1 transition-transform"></i>
                </button>

                <button onclick="triggerScan()" class="p-5 rounded-2xl bg-gray-900 border border-gray-800 hover:border-gray-700 text-white font-semibold hover:bg-gray-800/70 transition-all flex items-center gap-4">
                    <div class="w-12 h-12 rounded-xl bg-blue-950/60 text-blue-400 flex items-center justify-center text-xl">
                        <i class="fa-solid fa-radar"></i>
                    </div>
                    <div class="text-left">
                        <div class="font-bold">Scan Catalog</div>
                        <div class="text-xs text-gray-400 font-normal">Detect current anomalies</div>
                    </div>
                </button>

                <button onclick="triggerReset()" class="p-5 rounded-2xl bg-gray-900 border border-gray-800 hover:border-gray-700 text-white font-semibold hover:bg-gray-800/70 transition-all flex items-center gap-4">
                    <div class="w-12 h-12 rounded-xl bg-purple-950/60 text-purple-400 flex items-center justify-center text-xl">
                        <i class="fa-solid fa-rotate-left"></i>
                    </div>
                    <div class="text-left">
                        <div class="font-bold">Reset Demo State</div>
                        <div class="text-xs text-gray-400 font-normal">Seed 8 fresh anomalies</div>
                    </div>
                </button>
            </div>

            <!-- Health Metric KPI Cards -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-5">
                <div class="p-6 rounded-2xl bg-gray-900/90 border border-gray-800 glow-blue relative overflow-hidden">
                    <div class="flex justify-between items-start mb-2">
                        <span class="text-xs font-medium uppercase tracking-wider text-gray-400">Overall Governance Score</span>
                        <i class="fa-solid fa-chart-pie text-blue-400"></i>
                    </div>
                    <div id="score-overall" class="text-4xl font-extrabold text-blue-400 tracking-tight">--%</div>
                    <div class="w-full bg-gray-800 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="bar-overall" class="bg-blue-500 h-full rounded-full transition-all duration-700" style="width: 0%"></div>
                    </div>
                </div>

                <div class="p-6 rounded-2xl bg-gray-900/90 border border-gray-800 glow-green relative overflow-hidden">
                    <div class="flex justify-between items-start mb-2">
                        <span class="text-xs font-medium uppercase tracking-wider text-gray-400">Security & PII Masking</span>
                        <i class="fa-solid fa-lock text-emerald-400"></i>
                    </div>
                    <div id="score-security" class="text-4xl font-extrabold text-emerald-400 tracking-tight">--%</div>
                    <div class="w-full bg-gray-800 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="bar-security" class="bg-emerald-500 h-full rounded-full transition-all duration-700" style="width: 0%"></div>
                    </div>
                </div>

                <div class="p-6 rounded-2xl bg-gray-900/90 border border-gray-800 glow-purple relative overflow-hidden">
                    <div class="flex justify-between items-start mb-2">
                        <span class="text-xs font-medium uppercase tracking-wider text-gray-400">Documentation Coverage</span>
                        <i class="fa-solid fa-book text-purple-400"></i>
                    </div>
                    <div id="score-doc" class="text-4xl font-extrabold text-purple-400 tracking-tight">--%</div>
                    <div class="w-full bg-gray-800 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="bar-doc" class="bg-purple-500 h-full rounded-full transition-all duration-700" style="width: 0%"></div>
                    </div>
                </div>

                <div class="p-6 rounded-2xl bg-gray-900/90 border border-gray-800 relative overflow-hidden">
                    <div class="flex justify-between items-start mb-2">
                        <span class="text-xs font-medium uppercase tracking-wider text-gray-400">Domain Ownership</span>
                        <i class="fa-solid fa-user-shield text-amber-400"></i>
                    </div>
                    <div id="score-owner" class="text-4xl font-extrabold text-amber-400 tracking-tight">--%</div>
                    <div class="w-full bg-gray-800 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="bar-owner" class="bg-amber-500 h-full rounded-full transition-all duration-700" style="width: 0%"></div>
                    </div>
                </div>
            </div>

            <!-- Multi-Database Connectors & MCP Services -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <!-- Connectors Panel -->
                <div class="p-6 rounded-2xl bg-gray-900/80 border border-gray-800">
                    <h3 class="text-base font-semibold text-white mb-4 flex items-center gap-2">
                        <i class="fa-solid fa-database text-cyan-400"></i>
                        Connected Databases (4)
                    </h3>
                    <div class="space-y-3">
                        <div class="p-3 rounded-xl bg-gray-950/60 border border-gray-800/80 flex items-center justify-between">
                            <div class="flex items-center gap-3">
                                <i class="fa-solid fa-table-cells text-blue-400"></i>
                                <div>
                                    <div class="text-sm font-medium text-white">PostgreSQL Warehouse</div>
                                    <div class="text-xs text-gray-400">Relational SQL tables</div>
                                </div>
                            </div>
                            <span class="text-xs px-2 py-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/50">Online</span>
                        </div>

                        <div class="p-3 rounded-xl bg-gray-950/60 border border-gray-800/80 flex items-center justify-between">
                            <div class="flex items-center gap-3">
                                <i class="fa-solid fa-file-code text-green-400"></i>
                                <div>
                                    <div class="text-sm font-medium text-white">MongoDB Document Store</div>
                                    <div class="text-xs text-gray-400">JSON customer profiles</div>
                                </div>
                            </div>
                            <span class="text-xs px-2 py-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/50">Online</span>
                        </div>

                        <div class="p-3 rounded-xl bg-gray-950/60 border border-gray-800/80 flex items-center justify-between">
                            <div class="flex items-center gap-3">
                                <i class="fa-solid fa-cubes text-purple-400"></i>
                                <div>
                                    <div class="text-sm font-medium text-white">ChromaDB Vector Store</div>
                                    <div class="text-xs text-gray-400">RAG knowledge embeddings</div>
                                </div>
                            </div>
                            <span class="text-xs px-2 py-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/50">Online</span>
                        </div>

                        <div class="p-3 rounded-xl bg-gray-950/60 border border-gray-800/80 flex items-center justify-between">
                            <div class="flex items-center gap-3">
                                <i class="fa-solid fa-sitemap text-amber-400"></i>
                                <div>
                                    <div class="text-sm font-medium text-white">Atlan Active Catalog</div>
                                    <div class="text-xs text-gray-400">Unified metadata & lineage</div>
                                </div>
                            </div>
                            <span class="text-xs px-2 py-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/50">Online</span>
                        </div>
                    </div>
                </div>

                <!-- MCP Self-Healing Services Panel -->
                <div class="p-6 rounded-2xl bg-gray-900/80 border border-gray-800 lg:col-span-2">
                    <h3 class="text-base font-semibold text-white mb-4 flex items-center gap-2">
                        <i class="fa-solid fa-microchip text-indigo-400"></i>
                        Discovered MCP Self-Healing Microservices
                    </h3>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div class="p-4 rounded-xl bg-gray-950/60 border border-gray-800 flex flex-col justify-between">
                            <div>
                                <div class="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-1">mcp-pii-service</div>
                                <div class="text-sm font-medium text-white">PII & PCI Healer</div>
                                <p class="text-xs text-gray-400 mt-2">Regex sensitivity classification & dynamic cross-DB masking.</p>
                            </div>
                            <div class="text-xs text-gray-500 mt-4 border-t border-gray-800/80 pt-2">3 Tools Exposed</div>
                        </div>

                        <div class="p-4 rounded-xl bg-gray-950/60 border border-gray-800 flex flex-col justify-between">
                            <div>
                                <div class="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-1">mcp-metadata-service</div>
                                <div class="text-sm font-medium text-white">Metadata Enricher</div>
                                <p class="text-xs text-gray-400 mt-2">Business documentation curation & glossary term association.</p>
                            </div>
                            <div class="text-xs text-gray-500 mt-4 border-t border-gray-800/80 pt-2">3 Tools Exposed</div>
                        </div>

                        <div class="p-4 rounded-xl bg-gray-950/60 border border-gray-800 flex flex-col justify-between">
                            <div>
                                <div class="text-xs font-semibold text-cyan-400 uppercase tracking-wider mb-1">mcp-drift-service</div>
                                <div class="text-sm font-medium text-white">Semantic Drift Healer</div>
                                <p class="text-xs text-gray-400 mt-2">KPI schema drift diagnostics & formula alias remapping.</p>
                            </div>
                            <div class="text-xs text-gray-500 mt-4 border-t border-gray-800/80 pt-2">3 Tools Exposed</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Live Actions & Audit Log Feed -->
            <div class="p-6 rounded-2xl bg-gray-900/80 border border-gray-800">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-base font-semibold text-white flex items-center gap-2">
                        <i class="fa-solid fa-list-check text-emerald-400"></i>
                        Autonomous Remediation & Audit Feed
                    </h3>
                    <span id="feed-status" class="text-xs text-gray-400">Ready</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm text-gray-300">
                        <thead class="text-xs uppercase bg-gray-950/80 text-gray-400 border-b border-gray-800">
                            <tr>
                                <th class="px-4 py-3">Timestamp</th>
                                <th class="px-4 py-3">Action</th>
                                <th class="px-4 py-3">Asset</th>
                                <th class="px-4 py-3">Actor / MCP Service</th>
                                <th class="px-4 py-3">Reason / Remediation</th>
                            </tr>
                        </thead>
                        <tbody id="audit-tbody" class="divide-y divide-gray-800/50">
                            <tr>
                                <td colspan="5" class="px-4 py-6 text-center text-gray-500">Click 'Scan Catalog' or 'Execute Autonomous Self-Healing' to view live actions.</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </main>

        <script>
            async function fetchHealth() {
                try {
                    const res = await fetch('/api/v1/health');
                    const data = await res.json();
                    const s = data.governance_scores;
                    document.getElementById('score-overall').innerText = s.overall_score + '%';
                    document.getElementById('bar-overall').style.width = s.overall_score + '%';

                    document.getElementById('score-security').innerText = s.security_compliance_pct + '%';
                    document.getElementById('bar-security').style.width = s.security_compliance_pct + '%';

                    document.getElementById('score-doc').innerText = s.documentation_coverage_pct + '%';
                    document.getElementById('bar-doc').style.width = s.documentation_coverage_pct + '%';

                    document.getElementById('score-owner').innerText = s.ownership_coverage_pct + '%';
                    document.getElementById('bar-owner').style.width = s.ownership_coverage_pct + '%';
                } catch(e) {
                    console.error('Error fetching health:', e);
                }
            }

            async function fetchAudit() {
                try {
                    const res = await fetch('/api/v1/audit');
                    const data = await res.json();
                    const tbody = document.getElementById('audit-tbody');
                    if(data.audit_trail && data.audit_trail.length > 0) {
                        tbody.innerHTML = '';
                        data.audit_trail.slice(-8).reverse().forEach(item => {
                            const timeStr = item.timestamp.split('T')[1].slice(0, 8);
                            const row = document.createElement('tr');
                            row.className = 'hover:bg-gray-800/30 transition-colors';
                            row.innerHTML = `
                                <td class="px-4 py-3 font-mono text-xs text-gray-400">${timeStr} UTC</td>
                                <td class="px-4 py-3 font-semibold text-emerald-400">${item.action}</td>
                                <td class="px-4 py-3 text-white">${item.asset_name}</td>
                                <td class="px-4 py-3"><span class="px-2 py-0.5 rounded text-xs bg-indigo-950 text-indigo-300 border border-indigo-800/40">${item.actor}</span></td>
                                <td class="px-4 py-3 text-xs text-gray-300">${item.reason}</td>
                            `;
                            tbody.appendChild(row);
                        });
                    }
                } catch(e) {
                    console.error('Error fetching audit:', e);
                }
            }

            async function triggerHeal() {
                const btn = document.getElementById('btn-heal');
                btn.classList.add('opacity-50');
                document.getElementById('feed-status').innerText = 'Executing autonomous healing...';
                try {
                    const res = await fetch('/api/v1/heal', { method: 'POST' });
                    await res.json();
                    await fetchHealth();
                    await fetchAudit();
                    document.getElementById('feed-status').innerText = 'Self-Healing Cycle Completed!';
                } catch(e) {
                    console.error(e);
                } finally {
                    btn.classList.remove('opacity-50');
                }
            }

            async function triggerScan() {
                document.getElementById('feed-status').innerText = 'Scanning multi-database assets...';
                try {
                    await fetch('/api/v1/scan', { method: 'POST' });
                    await fetchHealth();
                    await fetchAudit();
                    document.getElementById('feed-status').innerText = 'Scan Complete';
                } catch(e) {
                    console.error(e);
                }
            }

            async function triggerReset() {
                document.getElementById('feed-status').innerText = 'Resetting catalog state...';
                try {
                    await fetch('/api/v1/reset', { method: 'POST' });
                    await fetchHealth();
                    await fetchAudit();
                    document.getElementById('feed-status').innerText = 'Catalog Reset to Initial Anomaly State';
                } catch(e) {
                    console.error(e);
                }
            }

            // Initial load
            fetchHealth();
            fetchAudit();
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)


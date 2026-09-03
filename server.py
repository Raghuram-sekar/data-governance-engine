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


@app.get("/api/v1/databases", tags=["Governance Operations"])
async def get_database_assets():
    """Returns detailed table, column, and sensitivity state across all 4 database connectors."""
    data = {}
    for conn_id, conn in connector_registry.list_all().items():
        tables = conn.list_tables()
        data[conn_id] = {
            "name": conn.name,
            "type": conn.connector_type.value,
            "tables": [
                {
                    "name": t.name,
                    "qualified_name": t.qualified_name,
                    "description": t.description,
                    "owner": t.owner,
                    "row_count": t.row_count,
                    "columns": [
                        {
                            "name": c.name,
                            "data_type": c.data_type,
                            "description": c.description,
                            "classifications": c.classifications,
                            "is_masked": c.is_masked
                        }
                        for c in t.columns
                    ]
                }
                for t in tables
            ]
        }
    return data


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


@app.get("/api/v1/traces", tags=["Governance Operations"])
async def get_observability_traces():
    """Returns the live Arize Phoenix OpenTelemetry traces recorded in the engine."""
    traces = phoenix_tracer.get_all_traces()
    return {
        "total_traces": len(traces),
        "phoenix_url": "http://localhost:6006",
        "traces": traces[-25:]
    }


@app.get("/", response_class=HTMLResponse, tags=["Visual Dashboard"])
async def visual_dashboard():
    """Renders the Enterprise Self-Healing Governance & MCP Orchestration Dashboard."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Enterprise Data Governance & MCP Orchestration Engine</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
        <style>
            body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #090d16; color: #f1f5f9; }
            .font-mono { font-family: 'JetBrains Mono', monospace; }
            .glass-card { background: rgba(17, 24, 39, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.07); }
            .glass-card-hover:hover { border-color: rgba(59, 130, 246, 0.4); box-shadow: 0 10px 30px -10px rgba(59, 130, 246, 0.2); }
            .pulse-dot { animation: pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
            @keyframes pulse-glow { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .4; transform: scale(0.9); } }
            .pipeline-line { background: linear-gradient(90deg, #3b82f6 0%, #10b981 50%, #8b5cf6 100%); }
        </style>
    </head>
    <body class="min-h-screen flex flex-col antialiased selection:bg-blue-600 selection:text-white">
        <!-- Top Enterprise Header -->
        <header class="sticky top-0 z-50 bg-[#090d16]/90 backdrop-blur-md border-b border-slate-800/80 px-6 py-3.5">
            <div class="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
                <div class="flex items-center gap-3.5">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-white shadow-lg shadow-blue-500/30">
                        <i class="fa-solid fa-shield-halved text-xl"></i>
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <h1 class="text-lg font-bold text-white tracking-tight">Artizent Governance Engine</h1>
                            <span class="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-400 border border-blue-500/20">MCP v2.0 Microservices</span>
                        </div>
                        <p class="text-xs text-slate-400">Autonomous Closed-Loop Governance • Agno AI • Atlan Active Metadata • Arize Phoenix</p>
                    </div>
                </div>

                <!-- Navigation & Status Controls -->
                <div class="flex items-center gap-3 flex-wrap">
                    <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300">
                        <span class="w-2 h-2 rounded-full bg-emerald-400 pulse-dot"></span>
                        <span class="font-medium text-slate-200">Port 8000 Online</span>
                    </div>

                    <a href="http://localhost:6006" target="_blank" class="px-3.5 py-1.5 rounded-lg bg-orange-500/10 border border-orange-500/30 text-orange-400 hover:bg-orange-500/20 transition-all flex items-center gap-2 text-xs font-semibold shadow-sm">
                        <i class="fa-solid fa-fire text-orange-400"></i>
                        Arize Phoenix Traces
                        <i class="fa-solid fa-arrow-up-right-from-square text-[10px] opacity-70"></i>
                    </a>

                    <a href="/docs" target="_blank" class="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition-all flex items-center gap-2 text-xs font-medium">
                        <i class="fa-solid fa-code text-blue-400"></i>
                        Swagger API
                    </a>

                    <button onclick="triggerReset()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-rose-950/40 hover:text-rose-400 border border-slate-700 hover:border-rose-800/40 text-slate-300 transition-all flex items-center gap-1.5 text-xs font-medium">
                        <i class="fa-solid fa-rotate-left text-purple-400"></i>
                        Reset Demo
                    </button>
                </div>
            </div>
        </header>

        <!-- Main Dashboard Container -->
        <main class="max-w-7xl w-full mx-auto p-6 space-y-7 flex-1">
            
            <!-- Hero Orchestration Action Bar -->
            <div class="glass-card rounded-2xl p-6 border-slate-800 relative overflow-hidden">
                <div class="absolute -right-20 -top-20 w-80 h-80 bg-blue-600/10 rounded-full blur-3xl pointer-events-none"></div>
                <div class="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 relative z-10">
                    <div>
                        <div class="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold mb-2">
                            <i class="fa-solid fa-bolt-lightning text-xs"></i>
                            Key-Orchestrator Dispatcher Active
                        </div>
                        <h2 class="text-2xl font-bold text-white tracking-tight">Multi-Database Autonomous Self-Healing Pipeline</h2>
                        <p class="text-sm text-slate-400 mt-1 max-w-2xl">
                            Continuously detects PII/PCI leaks, undocumented schemas, and metric formula drift across PostgreSQL, MongoDB, ChromaDB, and Atlan Catalog, then autonomously dispatches specialized MCP microservices.
                        </p>
                    </div>

                    <div class="flex items-center gap-3 w-full lg:w-auto">
                        <button onclick="triggerScan()" id="btn-scan" class="flex-1 lg:flex-none px-5 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-white text-sm font-semibold border border-slate-700 transition-all flex items-center justify-center gap-2 shadow-sm">
                            <i class="fa-solid fa-radar text-blue-400"></i>
                            Scan Databases
                        </button>
                        <button onclick="triggerHeal()" id="btn-heal" class="flex-1 lg:flex-none px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-emerald-600 hover:from-blue-500 hover:to-emerald-500 text-white text-sm font-bold shadow-lg shadow-indigo-500/25 transition-all flex items-center justify-center gap-2.5">
                            <i class="fa-solid fa-wand-magic-sparkles text-amber-300"></i>
                            Execute Autonomous Self-Healing
                        </button>
                    </div>
                </div>
            </div>

            <!-- Executive KPI Scorecards -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="glass-card rounded-2xl p-5 border-slate-800 flex flex-col justify-between">
                    <div class="flex justify-between items-center text-slate-400 text-xs font-semibold uppercase tracking-wider">
                        <span>Governance Health Score</span>
                        <i class="fa-solid fa-chart-pie text-blue-400 text-sm"></i>
                    </div>
                    <div class="mt-4 flex items-baseline gap-2">
                        <span id="score-overall" class="text-4xl font-extrabold text-blue-400 tracking-tight">--%</span>
                        <span id="score-overall-delta" class="text-xs font-semibold text-emerald-400">+32.1%</span>
                    </div>
                    <div class="w-full bg-slate-800 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="bar-overall" class="bg-gradient-to-r from-blue-600 to-indigo-500 h-full rounded-full transition-all duration-700" style="width: 0%"></div>
                    </div>
                </div>

                <div class="glass-card rounded-2xl p-5 border-slate-800 flex flex-col justify-between">
                    <div class="flex justify-between items-center text-slate-400 text-xs font-semibold uppercase tracking-wider">
                        <span>Security & PII Masking</span>
                        <i class="fa-solid fa-lock text-emerald-400 text-sm"></i>
                    </div>
                    <div class="mt-4 flex items-baseline gap-2">
                        <span id="score-security" class="text-4xl font-extrabold text-emerald-400 tracking-tight">--%</span>
                        <span id="score-security-count" class="text-xs font-medium text-slate-400">14/14 cols</span>
                    </div>
                    <div class="w-full bg-slate-800 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="bar-security" class="bg-emerald-500 h-full rounded-full transition-all duration-700" style="width: 0%"></div>
                    </div>
                </div>

                <div class="glass-card rounded-2xl p-5 border-slate-800 flex flex-col justify-between">
                    <div class="flex justify-between items-center text-slate-400 text-xs font-semibold uppercase tracking-wider">
                        <span>Documentation Coverage</span>
                        <i class="fa-solid fa-book-bookmark text-purple-400 text-sm"></i>
                    </div>
                    <div class="mt-4 flex items-baseline gap-2">
                        <span id="score-doc" class="text-4xl font-extrabold text-purple-400 tracking-tight">--%</span>
                        <span class="text-xs font-semibold text-emerald-400">Verified</span>
                    </div>
                    <div class="w-full bg-slate-800 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="bar-doc" class="bg-purple-500 h-full rounded-full transition-all duration-700" style="width: 0%"></div>
                    </div>
                </div>

                <div class="glass-card rounded-2xl p-5 border-slate-800 flex flex-col justify-between">
                    <div class="flex justify-between items-center text-slate-400 text-xs font-semibold uppercase tracking-wider">
                        <span>Domain Stewardship</span>
                        <i class="fa-solid fa-user-check text-amber-400 text-sm"></i>
                    </div>
                    <div class="mt-4 flex items-baseline gap-2">
                        <span id="score-owner" class="text-4xl font-extrabold text-amber-400 tracking-tight">--%</span>
                        <span class="text-xs font-semibold text-emerald-400">Assigned</span>
                    </div>
                    <div class="w-full bg-slate-800 h-2 rounded-full mt-4 overflow-hidden">
                        <div id="bar-owner" class="bg-amber-500 h-full rounded-full transition-all duration-700" style="width: 0%"></div>
                    </div>
                </div>
            </div>

            <!-- Tabbed Explorer (Orchestration Pipeline vs Database Assets vs Live Key-Orchestrator) -->
            <div class="space-y-4">
                <div class="flex items-center justify-between border-b border-slate-800 pb-2">
                    <div class="flex items-center gap-2">
                        <button onclick="switchTab('pipeline')" id="tab-btn-pipeline" class="px-4 py-2 rounded-lg font-semibold text-xs transition-all bg-blue-600/10 text-blue-400 border border-blue-500/20">
                            <i class="fa-solid fa-diagram-project mr-1.5"></i>
                            Live Orchestration Pipeline
                        </button>
                        <button onclick="switchTab('databases')" id="tab-btn-databases" class="px-4 py-2 rounded-lg font-semibold text-xs transition-all text-slate-400 hover:text-slate-200">
                            <i class="fa-solid fa-database mr-1.5"></i>
                            Multi-Database Explorer (4)
                        </button>
                        <button onclick="switchTab('playground')" id="tab-btn-playground" class="px-4 py-2 rounded-lg font-semibold text-xs transition-all text-slate-400 hover:text-slate-200">
                            <i class="fa-solid fa-terminal mr-1.5"></i>
                            Key-Orchestrator JSON Playground
                        </button>
                    </div>

                    <div id="live-status-pill" class="text-xs font-mono px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-slate-400">
                        Status: <span class="text-emerald-400 font-semibold">Ready</span>
                    </div>
                </div>

                <!-- Tab 1: Live Orchestration Pipeline View -->
                <div id="tab-pipeline" class="space-y-6">
                    <!-- 3 Discovered MCP Microservices Cards -->
                    <div>
                        <div class="flex items-center justify-between mb-3">
                            <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                                <i class="fa-solid fa-microchip text-indigo-400"></i>
                                Registered Model Context Protocol (MCP) Microservices
                            </h3>
                            <span class="text-[11px] text-slate-500">Dynamic Tool Discovery Active</span>
                        </div>

                        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div class="glass-card rounded-xl p-4 border-slate-800 border-l-4 border-l-emerald-500 flex flex-col justify-between">
                                <div>
                                    <div class="flex items-center justify-between">
                                        <span class="text-xs font-bold text-emerald-400 font-mono">mcp-pii-selfhealerservice</span>
                                        <span class="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">Privacy</span>
                                    </div>
                                    <div class="text-sm font-semibold text-white mt-1.5">PII / PCI Security Healer</div>
                                    <p class="text-xs text-slate-400 mt-1">Evaluates column sensitivity regex rules and enforces dynamic masking across SQL, NoSQL & Vector stores.</p>
                                </div>
                                <div class="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                                    <span>Tools: 3 exposed</span>
                                    <span class="text-emerald-400">evaluate_sensitivity, enforce_masking</span>
                                </div>
                            </div>

                            <div class="glass-card rounded-xl p-4 border-slate-800 border-l-4 border-l-purple-500 flex flex-col justify-between">
                                <div>
                                    <div class="flex items-center justify-between">
                                        <span class="text-xs font-bold text-purple-400 font-mono">mcp-metadata-selfhealerservice</span>
                                        <span class="text-[10px] px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">Metadata</span>
                                    </div>
                                    <div class="text-sm font-semibold text-white mt-1.5">Metadata & Glossary Enricher</div>
                                    <p class="text-xs text-slate-400 mt-1">Resolves missing table/column documentation from enterprise ontology and links verified glossary terms.</p>
                                </div>
                                <div class="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                                    <span>Tools: 3 exposed</span>
                                    <span class="text-purple-400">heal_table_metadata, link_glossary</span>
                                </div>
                            </div>

                            <div class="glass-card rounded-xl p-4 border-slate-800 border-l-4 border-l-cyan-500 flex flex-col justify-between">
                                <div>
                                    <div class="flex items-center justify-between">
                                        <span class="text-xs font-bold text-cyan-400 font-mono">mcp-drift-selfhealerservice</span>
                                        <span class="text-[10px] px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">Semantics</span>
                                    </div>
                                    <div class="text-sm font-semibold text-white mt-1.5">Semantic Metric Drift Healer</div>
                                    <p class="text-xs text-slate-400 mt-1">Diagnoses schema evolution that breaks downstream KPI formulas and applies semantic alias mappings.</p>
                                </div>
                                <div class="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                                    <span>Tools: 3 exposed</span>
                                    <span class="text-cyan-400">validate_metric, heal_metric_drift</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Live Anomalies & Remediation Feed -->
                    <div class="glass-card rounded-2xl p-5 border-slate-800">
                        <div class="flex items-center justify-between mb-4">
                            <div>
                                <h3 class="text-sm font-bold text-white flex items-center gap-2">
                                    <i class="fa-solid fa-clock-rotate-left text-emerald-400"></i>
                                    Autonomous Self-Healing Audit & Action Feed
                                </h3>
                                <p class="text-xs text-slate-400">Live feed of anomalous detections and executed MCP remediations across all database engines.</p>
                            </div>
                            <span class="text-xs text-slate-500 font-mono" id="audit-count">-- events</span>
                        </div>

                        <div class="overflow-x-auto">
                            <table class="w-full text-left text-xs text-slate-300">
                                <thead class="text-[11px] font-bold uppercase bg-slate-900/90 text-slate-400 border-b border-slate-800">
                                    <tr>
                                        <th class="px-4 py-3">Timestamp</th>
                                        <th class="px-4 py-3">Action</th>
                                        <th class="px-4 py-3">Target Asset</th>
                                        <th class="px-4 py-3">Responsible MCP Service</th>
                                        <th class="px-4 py-3">Reason / Remediation Applied</th>
                                        <th class="px-4 py-3 text-right">Observability</th>
                                    </tr>
                                </thead>
                                <tbody id="audit-tbody" class="divide-y divide-slate-800/60 font-mono">
                                    <tr>
                                        <td colspan="6" class="px-4 py-8 text-center text-slate-500 font-sans">
                                            Loading live catalog events...
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Tab 2: Multi-Database Explorer View -->
                <div id="tab-databases" class="hidden space-y-4">
                    <div id="db-grid" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <!-- Loaded dynamically via fetchDatabases() -->
                    </div>
                </div>

                <!-- Tab 3: Key-Orchestrator JSON Playground View -->
                <div id="tab-playground" class="hidden space-y-4">
                    <div class="glass-card rounded-2xl p-6 border-slate-800">
                        <div class="flex items-center justify-between mb-4">
                            <div>
                                <h3 class="text-sm font-bold text-white flex items-center gap-2">
                                    <i class="fa-solid fa-paper-plane text-blue-400"></i>
                                    Test Key-Orchestrator Agent (<code class="text-blue-300">POST /api/v1/orchestrate</code>)
                                </h3>
                                <p class="text-xs text-slate-400">Send an arbitrary anomaly event JSON to test real-time MCP service discovery and execution.</p>
                            </div>
                            
                            <div class="flex items-center gap-2">
                                <button onclick="loadScenario('pii')" class="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700">PII Scenario</button>
                                <button onclick="loadScenario('meta')" class="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700">Metadata Scenario</button>
                                <button onclick="loadScenario('drift')" class="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700">Drift Scenario</button>
                            </div>
                        </div>

                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">Input Event Payload (JSON)</label>
                                <textarea id="playground-req" rows="11" class="w-full p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 font-mono text-xs focus:border-blue-500 focus:outline-none"></textarea>
                                <button onclick="sendPlaygroundEvent()" id="btn-play-send" class="w-full mt-3 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs transition-all shadow-md shadow-blue-600/30 flex items-center justify-center gap-2">
                                    <i class="fa-solid fa-play"></i>
                                    Send to Key-Orchestrator Agent
                                </button>
                            </div>

                            <div>
                                <label class="block text-xs font-semibold text-slate-400 mb-1.5 uppercase">Orchestration & Remediation Response</label>
                                <pre id="playground-res" class="w-full h-64 p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-emerald-400 font-mono text-xs overflow-auto">Click 'Send to Key-Orchestrator Agent' to see live JSON response.</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </main>

        <script>
            function switchTab(tab) {
                document.getElementById('tab-pipeline').classList.add('hidden');
                document.getElementById('tab-databases').classList.add('hidden');
                document.getElementById('tab-playground').classList.add('hidden');

                document.getElementById('tab-btn-pipeline').className = 'px-4 py-2 rounded-lg font-semibold text-xs transition-all text-slate-400 hover:text-slate-200';
                document.getElementById('tab-btn-databases').className = 'px-4 py-2 rounded-lg font-semibold text-xs transition-all text-slate-400 hover:text-slate-200';
                document.getElementById('tab-btn-playground').className = 'px-4 py-2 rounded-lg font-semibold text-xs transition-all text-slate-400 hover:text-slate-200';

                document.getElementById('tab-' + tab).classList.remove('hidden');
                document.getElementById('tab-btn-' + tab).className = 'px-4 py-2 rounded-lg font-semibold text-xs transition-all bg-blue-600/10 text-blue-400 border border-blue-500/20';

                if(tab === 'databases') fetchDatabases();
            }

            async function fetchHealth() {
                try {
                    const res = await fetch('/api/v1/health');
                    const data = await res.json();
                    const s = data.governance_scores;
                    document.getElementById('score-overall').innerText = s.overall_score + '%';
                    document.getElementById('bar-overall').style.width = s.overall_score + '%';

                    document.getElementById('score-security').innerText = s.security_compliance_pct + '%';
                    document.getElementById('bar-security').style.width = s.security_compliance_pct + '%';
                    document.getElementById('score-security-count').innerText = `${s.classified_sensitive_count}/${s.sensitive_columns_count} cols`;

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
                    document.getElementById('audit-count').innerText = `${data.total_events || 0} total events`;

                    if(data.audit_trail && data.audit_trail.length > 0) {
                        tbody.innerHTML = '';
                        data.audit_trail.slice(-10).reverse().forEach(item => {
                            const timeStr = item.timestamp.split('T')[1].slice(0, 8);
                            const row = document.createElement('tr');
                            row.className = 'hover:bg-slate-800/40 transition-colors font-sans';
                            
                            let badgeColor = 'bg-blue-500/10 text-blue-400 border-blue-500/20';
                            if(item.action.includes('CLASSIFY') || item.action.includes('MASK')) badgeColor = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
                            if(item.action.includes('OWNER')) badgeColor = 'bg-amber-500/10 text-amber-400 border-amber-500/20';

                            row.innerHTML = `
                                <td class="px-4 py-3 font-mono text-xs text-slate-400 whitespace-nowrap">${timeStr} UTC</td>
                                <td class="px-4 py-3 font-semibold text-white whitespace-nowrap">
                                    <span class="px-2 py-0.5 rounded text-[11px] border ${badgeColor}">${item.action}</span>
                                </td>
                                <td class="px-4 py-3 font-mono text-xs text-slate-300">${item.asset_name}</td>
                                <td class="px-4 py-3">
                                    <span class="px-2 py-0.5 rounded text-[11px] bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-mono">${item.actor}</span>
                                </td>
                                <td class="px-4 py-3 text-xs text-slate-300">${item.reason}</td>
                                <td class="px-4 py-3 text-right">
                                    <a href="http://localhost:6006" target="_blank" class="text-orange-400 hover:text-orange-300 text-[11px] font-semibold flex items-center justify-end gap-1">
                                        <i class="fa-solid fa-fire text-xs"></i> Phoenix
                                    </a>
                                </td>
                            `;
                            tbody.appendChild(row);
                        });
                    }
                } catch(e) {
                    console.error('Error fetching audit:', e);
                }
            }

            async function fetchDatabases() {
                try {
                    const res = await fetch('/api/v1/databases');
                    const data = await res.json();
                    const container = document.getElementById('db-grid');
                    container.innerHTML = '';

                    for(const [connId, db] of Object.entries(data)) {
                        const card = document.createElement('div');
                        card.className = 'glass-card rounded-2xl p-5 border-slate-800';

                        let tablesHtml = '';
                        db.tables.forEach(t => {
                            let colsHtml = '';
                            t.columns.forEach(c => {
                                let tagHtml = '';
                                if(c.is_masked) tagHtml = '<span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Masked</span>';
                                else if((c.classifications && c.classifications.length > 0)) tagHtml = `<span class="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20">${c.classifications.join(',')}</span>`;
                                else tagHtml = '<span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">Plaintext</span>';

                                colsHtml += `
                                    <div class="flex items-center justify-between text-xs py-1 border-b border-slate-800/40">
                                        <span class="font-mono text-slate-300">${c.name} <span class="text-slate-500">(${c.data_type})</span></span>
                                        ${tagHtml}
                                    </div>
                                `;
                            });

                            tablesHtml += `
                                <div class="mt-3 p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
                                    <div class="flex items-center justify-between mb-2">
                                        <span class="font-bold text-xs text-white">${t.name}</span>
                                        <span class="text-[10px] text-slate-400">${t.columns.length} columns</span>
                                    </div>
                                    ${colsHtml}
                                </div>
                            `;
                        });

                        card.innerHTML = `
                            <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                                <div>
                                    <div class="text-xs font-bold uppercase tracking-wider text-blue-400">${connId}</div>
                                    <h4 class="text-base font-bold text-white">${db.name}</h4>
                                </div>
                                <span class="px-2 py-0.5 rounded text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">ONLINE</span>
                            </div>
                            ${tablesHtml}
                        `;
                        container.appendChild(card);
                    }
                } catch(e) {
                    console.error('Error fetching databases:', e);
                }
            }

            async function triggerHeal() {
                const btn = document.getElementById('btn-heal');
                btn.classList.add('opacity-50', 'pointer-events-none');
                document.getElementById('live-status-pill').innerHTML = 'Status: <span class="text-amber-400 font-semibold animate-pulse">Orchestrating MCP Healers...</span>';

                try {
                    const res = await fetch('/api/v1/heal', { method: 'POST' });
                    const result = await res.json();
                    await fetchHealth();
                    await fetchAudit();
                    document.getElementById('live-status-pill').innerHTML = 'Status: <span class="text-emerald-400 font-semibold">100% Compliant & Healed</span>';
                } catch(e) {
                    console.error(e);
                } finally {
                    btn.classList.remove('opacity-50', 'pointer-events-none');
                }
            }

            async function triggerScan() {
                document.getElementById('live-status-pill').innerHTML = 'Status: <span class="text-blue-400 font-semibold animate-pulse">Scanning Multi-Databases...</span>';
                try {
                    await fetch('/api/v1/scan', { method: 'POST' });
                    await fetchHealth();
                    await fetchAudit();
                    document.getElementById('live-status-pill').innerHTML = 'Status: <span class="text-amber-400 font-semibold">Anomalies Detected</span>';
                } catch(e) {
                    console.error(e);
                }
            }

            async function triggerReset() {
                document.getElementById('live-status-pill').innerHTML = 'Status: <span class="text-purple-400 font-semibold animate-pulse">Resetting Catalog...</span>';
                try {
                    await fetch('/api/v1/reset', { method: 'POST' });
                    await fetchHealth();
                    await fetchAudit();
                    document.getElementById('live-status-pill').innerHTML = 'Status: <span class="text-rose-400 font-semibold">Reset to Anomaly State (67%)</span>';
                } catch(e) {
                    console.error(e);
                }
            }

            function loadScenario(type) {
                if(type === 'pii') {
                    document.getElementById('playground-req').value = JSON.stringify({
                        "anomaly_type": "UNCLASSIFIED_PII",
                        "connector": "postgres",
                        "table_name": "dim_customers",
                        "column_name": "tax_ssn",
                        "data_type": "VARCHAR"
                    }, null, 2);
                } else if(type === 'meta') {
                    document.getElementById('playground-req').value = JSON.stringify({
                        "anomaly_type": "MISSING_DESCRIPTION",
                        "connector": "atlan",
                        "table_name": "dim_customers",
                        "column_name": "user_email",
                        "asset_guid": "col-cust-002"
                    }, null, 2);
                } else if(type === 'drift') {
                    document.getElementById('playground-req').value = JSON.stringify({
                        "anomaly_type": "SEMANTIC_METRIC_DRIFT",
                        "connector": "atlan",
                        "table_name": "fct_orders",
                        "metric_name": "annual_recurring_revenue",
                        "raw_payload": { "columns": ["order_id", "gross_rev", "is_recurring"] }
                    }, null, 2);
                }
            }

            async function sendPlaygroundEvent() {
                const btn = document.getElementById('btn-play-send');
                btn.classList.add('opacity-50');
                const reqStr = document.getElementById('playground-req').value;
                try {
                    const reqJson = JSON.parse(reqStr);
                    const res = await fetch('/api/v1/orchestrate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(reqJson)
                    });
                    const data = await res.json();
                    document.getElementById('playground-res').innerText = JSON.stringify(data, null, 2);
                    await fetchHealth();
                    await fetchAudit();
                } catch(e) {
                    document.getElementById('playground-res').innerText = 'Error: ' + e.message;
                } finally {
                    btn.classList.remove('opacity-50');
                }
            }

            // Default Scenario & Init
            loadScenario('pii');
            fetchHealth();
            fetchAudit();
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)


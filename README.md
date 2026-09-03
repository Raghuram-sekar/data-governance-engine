# 🏛️ Autonomous Self-Healing Multi-Database Governance & Observability Engine
### Powered by **Agno** + **FastAPI & FastMCP** + **Atlan Active Metadata** + **Semantic Policy Engine** + **Arize Phoenix**

An enterprise-grade, closed-loop data governance microservice platform that autonomously detects, diagnoses, and remediates data decay, untagged PII/PCI exposure, missing documentation, unassigned stewardship, and semantic metric/schema drift across SQL, NoSQL, Vector DBs, and Metadata Catalogs.

---

## 🏗️ System Architecture

```
                                  ┌───────────────────────────────────────────────┐
                                  │   Incoming Webhook / API Clients (JSON)       │
                                  └───────────────────────┬───────────────────────┘
                                                          │ POST /api/v1/orchestrate
                                                          ▼
                                  ┌───────────────────────────────────────────────┐
                                  │   FastAPI Server + Key-Orchestrator Agent     │
                                  └───────────────────────┬───────────────────────┘
                                                          │
                               ┌──────────────────────────┴──────────────────────────┐
                               │ Dynamic MCP Service Discovery (services/mcp_registry)│
                               └──────┬───────────────────┬───────────────────┬──────┘
                                      │                   │                   │
                                      ▼                   ▼                   ▼
    ┌───────────────────────────────────┐ ┌─────────────────────────────────┐ ┌─────────────────────────────────┐
    │   mcp-pii-selfhealerservice       │ │ mcp-metadata-selfhealerservice  │ │  mcp-drift-selfhealerservice    │
    │ • evaluate_column_sensitivity     │ │ • lookup_semantic_glossary_term │ │ • validate_metric_semantic_heal │
    │ • apply_atlan_classification      │ │ • update_atlan_description      │ │ • resolve_metric_schema_drift   │
    │ • apply_database_data_masking     │ │ • assign_domain_steward         │ │ • register_semantic_alias       │
    └─────────────────┬─────────────────┘ └───────────────┬─────────────────┘ └───────────────┬─────────────────┘
                      │                                   │                                   │
                      └───────────────────────────────────┼───────────────────────────────────┘
                                                          │ (OpenTelemetry Spans)
                                                          ▼
                               ┌───────────────────────────────────────────────┐
                               │         Arize Phoenix Observability           │
                               │ • OpenTelemetry Spans via gRPC (Port 4317)    │
                               │ • Live Agent Trace UI at http://localhost:6006│
                               └───────────────────────────────────────────────┘
```

---

## 🚀 Key Features & Capabilities

1. **Self-Healing Agents as MCP Microservices**:
   * All specialist agents are wrapped as standardized **Model Context Protocol (MCP)** microservices (`mcp-pii-selfhealerservice`, `mcp-metadata-selfhealerservice`, `mcp-drift-selfhealerservice`).
   * Supports dynamic capability and tool discovery via standard schemas.
2. **FastAPI Web Server & Key-Orchestrator Routing**:
   * Central `POST /api/v1/orchestrate` endpoint that receives JSON anomaly payloads, dynamically discovers the appropriate MCP service, and dispatches remediation arguments.
   * Interactive Swagger UI documentation at `http://localhost:8000/docs`.
3. **Autonomous PII/PCI Sensitivity & Dynamic Masking**:
   * Scans columns across relational tables, document fields, and vector chunk metadata against regex sensitivity rules.
   * Autonomously classifies sensitive attributes (`PII`, `PCI`, `FINANCIAL`) and enforces dynamic column/document masking.
4. **Automated Documentation & Business Glossary Curation**:
   * Identifies undocumented assets and missing owners.
   * Auto-populates business descriptions from the semantic ontology, links canonical glossary terms, and assigns domain data stewards.
5. **Semantic Metric & Schema Drift Healing**:
   * Evaluates KPI health (e.g. `Annual Recurring Revenue`).
   * Detects physical schema changes (e.g. `order_total` renamed to `gross_rev`) and automatically registers alias mappings to restore metric integrity.
6. **Multi-Database Cross-Engine Protection**:
   * Native adapters for **PostgreSQL**, **MongoDB**, **ChromaDB**, and **Atlan Active Catalog**.
7. **Production-Grade OpenTelemetry Observability**:
   * Native gRPC trace streaming to **Arize Phoenix** (`http://localhost:6006`) with rich input/output JSON payloads and execution latency tracking.
8. **Immutable Atlan Audit Logging**:
   * Every autonomous action, reason, actor, and before/after state is recorded in a persistent audit trail.

---

## 📁 Repository Structure

```
├── agents/                       # Agno AI Specialist Agents & Orchestrator
│   ├── orchestrator.py           # Master Governance Orchestrator
│   ├── pii_healer.py             # PII/PCI Classification & Dynamic Masking Agent
│   ├── metadata_enricher.py      # Documentation, Glossary & Owner Curation Agent
│   ├── drift_healer.py           # Schema Evolution & Metric Drift Healing Agent
│   └── tools/                    # Function-calling tools bound to Agno agents
│       ├── atlan_tools.py        # Atlan Catalog manipulation tools
│       └── semantic_tools.py     # Semantic Policy evaluation tools
├── services/                     # Model Context Protocol (MCP) Microservices Layer
│   ├── mcp_base.py               # BaseMCPService interface & Pydantic schemas
│   ├── mcp_pii_service.py        # mcp-pii-selfhealerservice implementation
│   ├── mcp_metadata_service.py   # mcp-metadata-selfhealerservice implementation
│   ├── mcp_drift_service.py      # mcp-drift-selfhealerservice implementation
│   └── mcp_registry.py           # Dynamic MCP Discovery & Dispatch Registry
├── atlan_integration/            # Atlan Active Metadata Platform Integration
│   ├── client.py                 # Unified Atlan client gateway
│   ├── mock_client.py            # Local catalog simulator with persistent state
│   └── models.py                 # Pydantic schemas for tables, columns & audit log
├── config/                       # Application Configuration & Model Factory
│   ├── settings.py               # Pydantic settings management (.env)
│   └── model_factory.py          # Agno model provider (Ollama, Gemini, OpenAI)
├── connectors/                   # Modular Multi-Database Storage Adapters
│   ├── base.py                   # BaseConnector abstract class
│   ├── relational.py             # PostgreSQL / SQLite Relational Adapter
│   ├── nosql.py                  # MongoDB JSON Document Store Adapter
│   ├── vector.py                 # ChromaDB Vector Store Adapter (RAG Embeddings)
│   └── atlan.py                  # Atlan Active Catalog Adapter
├── engine/                       # Core Self-Healing Loop & Anomaly Detection
│   ├── detector.py               # Multi-database anomaly scanner
│   ├── loop.py                   # Closed-loop self-healing engine & health metrics
│   └── yaml_runner.py            # Declarative YAML checkpoint executor
├── observability/                # Arize Phoenix OpenTelemetry Tracing
│   └── phoenix_tracer.py         # OTel gRPC exporter & span manager
├── semantics/                    # Enterprise Business Ontology & Policy Layer
│   ├── engine.py                 # Semantic Policy Engine & metric validator
│   ├── models.py                 # Pydantic models for glossary & rules
│   └── ontology.json             # Declarative rules, glossary & KPI specs
├── tests/                        # Comprehensive Pytest Suite
│   ├── test_mcp_services_and_api.py # MCP services & FastAPI tests
│   ├── test_semantics.py         # Ontology & sensitivity rule tests
│   ├── test_pii_healing.py       # PII security healing tests
│   ├── test_metadata_enrichment.py# Documentation & glossary linking tests
│   ├── test_connectors_and_yaml.py# Multi-database & YAML runner tests
│   └── test_engine_loop.py       # End-to-end self-healing loop tests
├── server.py                     # FastAPI Web Application & Orchestrator API
├── cli.py                        # CLI Application powered by Typer & Rich
├── governance.yaml               # Declarative governance checkpoint specification
├── requirements.txt              # Project dependencies
└── README.md                     # Documentation
```

---

## 🛠️ Quickstart Guide

### 1. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/Raghuram-sekar/data-governance-engine.git
cd data-governance-engine
pip install -r requirements.txt
```

### 2. Start the FastAPI + MCP Server
Launch the FastAPI web server on port 8000:
```bash
python cli.py serve --port 8000
```
Open **[http://localhost:8000/docs](http://localhost:8000/docs)** to view the interactive Swagger API docs.

---

## 🌐 API Endpoints & MCP Usage

### 1. Send Anomaly to Key-Orchestrator Agent
`POST /api/v1/orchestrate`
```bash
curl -X POST http://localhost:8000/api/v1/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "anomaly_type": "UNCLASSIFIED_PII",
    "connector": "postgres",
    "table_name": "dim_customers",
    "column_name": "tax_ssn",
    "data_type": "VARCHAR"
  }'
```

### 2. Discover Registered MCP Services
`GET /api/v1/mcp/services`
```bash
curl http://localhost:8000/api/v1/mcp/services
```

---

## 💻 CLI Commands

* **Run End-to-End Demo:** `python cli.py demo`
* **Launch Web Server:** `python cli.py serve --port 8000`
* **List MCP Services:** `python cli.py mcp`
* **Scan Catalog & Databases:** `python cli.py scan`
* **Trigger Healing Cycle:** `python cli.py heal`
* **View Audit Trail:** `python cli.py audit`
* **Launch Phoenix Dashboard:** `python cli.py phoenix` (Open `http://localhost:6006`)

---

## 🧪 Running Tests

Execute the complete automated test suite (19 test cases):
```bash
pytest tests/ -v
```

---

## 📄 License
Apache-2.0 License.

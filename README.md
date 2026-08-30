# 🏛️ Autonomous Self-Healing Multi-Database Governance & Observability Engine
### Powered by **Agno** + **Atlan Active Metadata** + **Semantic Policy Engine** + **Arize Phoenix**

An enterprise-grade, closed-loop data governance platform that autonomously detects, diagnoses, and remediates data decay, untagged PII/PCI exposure, missing documentation, unassigned stewardship, and semantic metric/schema drift across SQL, NoSQL, Vector DBs, and Metadata Catalogs.

---

## 🏗️ System Architecture

```
                                  ┌───────────────────────────────────────────────┐
                                  │      Agno Multi-Agent Orchestrator Layer      │
                                  │  ┌────────────────────┬────────────────────┐  │
                                  │  │ PIISecurityHealer  │  MetadataEnricher  │  │
                                  │  ├────────────────────┼────────────────────┤  │
                                  │  │ SemanticDriftHealer│ GovernanceOrchestr │  │
                                  │  └─────────┬──────────┴─────────┬──────────┘  │
                                  └────────────┼────────────────────┼─────────────┘
                                               │                    │
                        ┌──────────────────────▼───────┐    ┌───────▼──────────────────────┐
                        │    Semantic Policy Engine    │    │    Atlan Active Metadata     │
                        │ • Enterprise Glossary        │    │ • Unified Catalog Assets     │
                        │ • PII/PCI Sensitivity Rules  │    │ • Lineage & Masking Policies │
                        │ • Metric & KPI Specifications│    │ • Immutable Audit Logs       │
                        └──────────────────────┬───────┘    └───────┬──────────────────────┘
                                               │                    │
                                  ┌────────────▼────────────────────▼─────────────┐
                                  │       Multi-Database Connector Adapters       │
                                  │  ┌───────────────┬─────────────────────────┐  │
                                  │  │ PostgreSQL    │ MongoDB (JSON NoSQL)    │  │
                                  │  ├───────────────┼─────────────────────────┤  │
                                  │  │ ChromaDB (RAG)│ Atlan Active Catalog    │  │
                                  │  └───────────────┴─────────────────────────┘  │
                                  └───────────────────────┬───────────────────────┘
                                                          │
                                                          ▼
                                  ┌───────────────────────────────────────────────┐
                                  │         Arize Phoenix Observability           │
                                  │ • OpenTelemetry Spans via gRPC (Port 4317)    │
                                  │ • Live Agent Trace UI at http://localhost:6006│
                                  └───────────────────────────────────────────────┘
```

---

## 🚀 Key Features & Capabilities

1. **Autonomous PII/PCI Sensitivity & Dynamic Masking**:
   * Scans columns across relational tables, document fields, and vector chunk metadata against regex sensitivity rules.
   * Autonomously classifies sensitive attributes (`PII`, `PCI`, `FINANCIAL`) and enforces dynamic column/document masking.
2. **Automated Documentation & Business Glossary Curation**:
   * Identifies undocumented assets and missing owners.
   * Auto-populates business descriptions from the semantic ontology, links canonical glossary terms, and assigns domain data stewards.
3. **Semantic Metric & Schema Drift Healing**:
   * Evaluates KPI health (e.g. `Annual Recurring Revenue`).
   * Detects physical schema changes (e.g. `order_total` renamed to `gross_rev`) and automatically registers alias mappings to restore metric integrity.
4. **Multi-Database Cross-Engine Protection**:
   * Native adapters for **PostgreSQL**, **MongoDB**, **ChromaDB**, and **Atlan Active Catalog**.
5. **Production-Grade OpenTelemetry Observability**:
   * Native gRPC trace streaming to **Arize Phoenix** (`http://localhost:6006`) with rich input/output JSON payloads and execution latency tracking.
6. **Immutable Atlan Audit Logging**:
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
│   ├── test_semantics.py         # Ontology & sensitivity rule tests
│   ├── test_pii_healing.py       # PII security healing tests
│   ├── test_metadata_enrichment.py# Documentation & glossary linking tests
│   ├── test_connectors_and_yaml.py# Multi-database & YAML runner tests
│   └── test_engine_loop.py       # End-to-end self-healing loop tests
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
git clone https://github.com/your-org/data-governance-engine.git
cd data-governance-engine
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env` to configure model providers or Atlan API credentials:
```bash
cp .env.example .env
```
*(By default, the system runs with local Ollama or deterministic semantic reasoning out of the box with zero external setup).*

---

## 💻 CLI Commands

### 🎬 Run the Full End-to-End Demo
Executes the full 6-step self-healing lifecycle (Reset $\rightarrow$ Connectors $\rightarrow$ Initial Scan $\rightarrow$ Agno Multi-Agent Healing $\rightarrow$ Verification Scan $\rightarrow$ Audit Trail):
```bash
python cli.py demo
```

### 🔍 Scan Catalog & Connected Databases
```bash
python cli.py scan
```

### 🪄 Trigger Autonomous Healing Cycle
```bash
python cli.py heal
```

### 📋 View Immutable Audit Trail
```bash
python cli.py audit
```

### 🔌 Inspect Multi-Database Connectors
```bash
python cli.py connectors
```

### 📜 Run Declarative Governance Checkpoints
```bash
python cli.py run_yaml --spec governance.yaml
```

### 🌐 Launch Arize Phoenix Observability UI
```bash
python cli.py phoenix
```
Then open `http://localhost:6006` to inspect live OpenTelemetry traces, execution latencies, and agent reasoning.

---

## 🧪 Running Tests

Execute the complete automated test suite:
```bash
pytest tests/ -v
```

---

## 📄 License
Apache-2.0 License.

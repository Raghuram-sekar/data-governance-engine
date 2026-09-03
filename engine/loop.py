import time
from typing import Dict, Any, List
from datetime import datetime, timezone
from .detector import GovernanceDetector
from agents.orchestrator import GovernanceOrchestrator
from atlan_integration.client import atlan_client
from connectors import connector_registry
from observability.phoenix_tracer import phoenix_tracer
from semantics.engine import semantic_engine
from services.mcp_registry import mcp_registry


class SelfHealingLoop:
    """
    Closed-loop Self-Healing Multi-Database Governance Engine.
    Orchestrates: Detect -> Diagnose (Agno) -> Heal (Postgres + Mongo + Chroma + Atlan) -> Audit & Report.
    """

    def __init__(self):
        self.detector = GovernanceDetector()
        self.orchestrator = GovernanceOrchestrator()

    def calculate_health_score(self) -> Dict[str, Any]:
        """Calculates multi-database governance compliance metrics across all 4 connectors."""
        total_tables = 0
        total_cols = 0
        sensitive_cols = 0
        protected_sensitive = 0
        documented_tables = 0
        owned_tables = 0
        documented_cols = 0

        for conn_id, conn in connector_registry.list_all().items():
            tables = conn.list_tables()
            total_tables += len(tables)
            for t in tables:
                if t.description and t.description.strip():
                    documented_tables += 1
                if t.owner or conn_id != "atlan":
                    owned_tables += 1
                
                total_cols += len(t.columns)
                for c in t.columns:
                    if c.description and c.description.strip():
                        documented_cols += 1
                    
                    match = semantic_engine.match_sensitivity(c.name, c.data_type)
                    if match:
                        sensitive_cols += 1
                        is_classified = match[0].classification.value in (c.classifications or [])
                        is_protected = is_classified or c.is_masked
                        if is_protected:
                            protected_sensitive += 1

        # Documentation coverage is evaluated on the Catalog layer (Atlan)
        catalog_conn = connector_registry.get("atlan")
        if catalog_conn:
            cat_tables = catalog_conn.list_tables()
            cat_tbl_count = len(cat_tables)
            cat_col_count = sum(len(t.columns) for t in cat_tables)
            cat_doc_tbls = sum(1 for t in cat_tables if t.description and t.description.strip())
            cat_doc_cols = sum(sum(1 for c in t.columns if c.description and c.description.strip()) for t in cat_tables)
            doc_score = ((cat_doc_tbls + cat_doc_cols) / (cat_tbl_count + cat_col_count) * 100) if (cat_tbl_count + cat_col_count) > 0 else 100
        else:
            doc_score = 100

        sec_score = (protected_sensitive / sensitive_cols * 100) if sensitive_cols > 0 else 100
        owner_score = (owned_tables / total_tables * 100) if total_tables > 0 else 100

        overall_score = (sec_score * 0.5) + (doc_score * 0.3) + (owner_score * 0.2)


        return {
            "overall_score": round(overall_score, 1),
            "security_compliance_pct": round(sec_score, 1),
            "documentation_coverage_pct": round(doc_score, 1),
            "ownership_coverage_pct": round(owner_score, 1),
            "total_tables": total_tables,
            "total_columns": total_cols,
            "sensitive_columns_count": sensitive_cols,
            "classified_sensitive_count": protected_sensitive
        }

    def execute_healing_cycle(self) -> Dict[str, Any]:
        """Executes full detection, diagnosis, and autonomous healing across all 4 database connectors."""
        pre_health = self.calculate_health_score()
        anomalies = self.detector.scan_catalog()

        healing_results = []
        tables = atlan_client.list_tables()

        for anom in anomalies:
            # Dynamically resolve appropriate MCP Self-Healing Microservice
            mcp_service = mcp_registry.route_for_anomaly(anom.anomaly_type.value)
            
            # 1. Non-Atlan Multi-Database Healing (Postgres, MongoDB, ChromaDB)
            if anom.asset_guid.startswith(("postgres:", "mongodb:", "chroma:")):
                parts = anom.asset_guid.split(":")
                conn_id = parts[0]
                tbl_name = parts[1] if len(parts) > 1 else ""
                col_name = parts[2] if len(parts) > 2 else ""

                if mcp_service and conn_id and tbl_name and col_name:
                    mcp_res = mcp_service.call_tool("enforce_database_masking", {
                        "connector_id": conn_id,
                        "table_name": tbl_name,
                        "column_name": col_name
                    })
                    healing_results.append({
                        "anomaly": anom.model_dump(),
                        "resolution": {
                            "status": mcp_res.status,
                            "service": mcp_service.metadata.service_name,
                            "action": f"DYNAMIC_MASKING_ENFORCED_{conn_id.upper()}",
                            "result": mcp_res.result
                        }
                    })
                time.sleep(0.05)

            # 2. Atlan Catalog Healing via MCP & Orchestrator
            else:
                tbl_context = {}
                if anom.asset_type.value == "Table":
                    tbl = next((t for t in tables if t.guid == anom.asset_guid), None)
                    if tbl:
                        tbl_context = {"table_name": tbl.name, "schema_name": tbl.schema_name, "columns": [c.name for c in tbl.columns]}
                elif anom.asset_type.value == "Column":
                    for tbl in tables:
                        if any(c.guid == anom.asset_guid for c in tbl.columns):
                            tbl_context = {"table_name": tbl.name, "schema_name": tbl.schema_name}
                            break

                res = self.orchestrator.handle_anomaly(anom, tbl_context)
                healing_results.append({
                    "anomaly": anom.model_dump(),
                    "resolution": res
                })
                time.sleep(0.15)

        post_health = self.calculate_health_score()
        audit_trail = atlan_client.get_audit_trail()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "anomalies_detected": len(anomalies),
            "anomalies_healed": len(healing_results),
            "pre_healing_health": pre_health,
            "post_healing_health": post_health,
            "healing_details": healing_results,
            "total_audit_actions": len(audit_trail)
        }

import uuid
from typing import List
from atlan_integration.client import atlan_client
from atlan_integration.models import GovernanceAnomaly, AnomalyType, AtlanAssetType
from semantics.engine import semantic_engine
from connectors import connector_registry


class GovernanceDetector:
    """
    Scans all connected multi-database assets (Atlan Catalog, PostgreSQL, MongoDB, ChromaDB)
    and flags governance gaps, PII leaks, and semantic metric drift by cross-referencing against Semantic Engine policies.
    """

    def scan_catalog(self) -> List[GovernanceAnomaly]:
        anomalies: List[GovernanceAnomaly] = []

        # 1. Scan All Connectors in Registry (PostgreSQL, MongoDB, ChromaDB, Atlan)
        for conn_id, conn in connector_registry.list_all().items():
            tables = conn.list_tables()
            for table in tables:
                # Check Table Documentation
                if not table.description or table.description.strip() == "":
                    guid = table.guid if hasattr(table, "guid") and table.guid else f"{conn_id}:{table.name}"
                    anomalies.append(GovernanceAnomaly(
                        id=f"anom-{uuid.uuid4().hex[:6]}",
                        anomaly_type=AnomalyType.MISSING_DESCRIPTION,
                        asset_guid=guid,
                        asset_name=f"[{conn_id.upper()}] {table.name}",
                        asset_type=AtlanAssetType.TABLE,
                        details=f"{conn.connector_type.value} Table '{table.qualified_name}' has no documentation.",
                        severity="MEDIUM",
                        suggested_action="Generate table description and business context."
                    ))

                # Check Table Owner (Catalog only)
                if not table.owner and conn_id == "atlan":
                    guid = table.guid if hasattr(table, "guid") and table.guid else f"{conn_id}:{table.name}"
                    anomalies.append(GovernanceAnomaly(
                        id=f"anom-{uuid.uuid4().hex[:6]}",
                        anomaly_type=AnomalyType.MISSING_OWNER,
                        asset_guid=guid,
                        asset_name=f"[{conn_id.upper()}] {table.name}",
                        asset_type=AtlanAssetType.TABLE,
                        details=f"Table '{table.qualified_name}' has no assigned owner or steward.",
                        severity="LOW",
                        suggested_action="Assign schema/domain data steward."
                    ))

                # Check Semantic Metric Health (Schema & KPI Drift)
                if table.name in ["fct_orders"] and conn_id == "atlan":
                    col_names = [c.name for c in table.columns]
                    metric_health = semantic_engine.check_metric_health("annual_recurring_revenue", col_names)
                    if not metric_health.get("is_healthy"):
                        guid = table.guid if hasattr(table, "guid") and table.guid else f"{conn_id}:{table.name}"
                        missing_str = ", ".join(metric_health.get("missing_columns", []))
                        anomalies.append(GovernanceAnomaly(
                            id=f"anom-{uuid.uuid4().hex[:6]}",
                            anomaly_type=AnomalyType.SEMANTIC_METRIC_DRIFT,
                            asset_guid=guid,
                            asset_name=f"[{conn_id.upper()}] {table.name}",
                            asset_type=AtlanAssetType.TABLE,
                            details=f"Table '{table.name}' schema drifted: column '{missing_str}' missing/renamed, breaking KPI '{metric_health.get('metric')}'.",
                            severity="HIGH",
                            suggested_action="Invoke Agno SemanticDriftHealer to resolve column mapping and restore metric formula."
                        ))

                # Check Columns for Sensitivity & Documentation
                for col in table.columns:
                    match = semantic_engine.match_sensitivity(col.name, col.data_type)
                    if match:
                        rule, conf = match
                        expected_class = rule.classification.value
                        is_classified = expected_class in (col.classifications or [])
                        is_protected = is_classified or col.is_masked

                        if not is_protected:
                            guid = col.guid if hasattr(col, "guid") and col.guid else f"{conn_id}:{table.name}:{col.name}"
                            anomalies.append(GovernanceAnomaly(
                                id=f"anom-{uuid.uuid4().hex[:6]}",
                                anomaly_type=AnomalyType.UNCLASSIFIED_PII,
                                asset_guid=guid,
                                asset_name=f"[{conn_id.upper()}] {table.name}.{col.name}",
                                asset_type=AtlanAssetType.COLUMN,
                                details=f"{conn.connector_type.value} sensitive column '{col.name}' matched {expected_class} rule ({conf*100:.0f}% confidence) but lacks protection/masking.",
                                severity="HIGH",
                                suggested_action=f"Apply '{expected_class}' classification and enforce masking."
                            ))

                    # Missing Column Description (Catalog only)
                    if conn_id == "atlan" and (not col.description or col.description.strip() == ""):
                        guid = col.guid if hasattr(col, "guid") and col.guid else f"{conn_id}:{table.name}:{col.name}"
                        anomalies.append(GovernanceAnomaly(
                            id=f"anom-{uuid.uuid4().hex[:6]}",
                            anomaly_type=AnomalyType.MISSING_DESCRIPTION,
                            asset_guid=guid,
                            asset_name=f"[{conn_id.upper()}] {col.name}",
                            asset_type=AtlanAssetType.COLUMN,
                            details=f"Column '{col.name}' has no description.",
                            severity="LOW",
                            suggested_action="Lookup semantic glossary and populate business definition."
                        ))

        return anomalies

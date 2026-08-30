import json
import uuid
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

from .models import (
    AtlanTable,
    AtlanColumn,
    AtlanAssetType,
    GovernanceAnomaly,
    AnomalyType,
    AtlanAuditRecord
)

STATE_FILE = Path(__file__).parent / ".mock_atlan_state.json"


class MockAtlanClient:
    """
    A full-featured mock client for Atlan Active Metadata Platform.
    Simulates databases, tables, columns, classifications, glossary links,
    lineage, and governance audit trails with local disk persistence.
    """

    def __init__(self):
        self.tables: Dict[str, AtlanTable] = {}
        self.columns: Dict[str, AtlanColumn] = {}
        self.audit_log: List[AtlanAuditRecord] = []
        self.lineage_graph: Dict[str, List[str]] = {}
        
        if not self._load_persisted_state():
            self.reset_catalog()

    def _save_persisted_state(self):
        """Saves current mock catalog state, audit trail, and semantic aliases to disk."""
        try:
            from semantics.engine import semantic_engine
            state = {
                "tables": {k: v.model_dump(mode="json") for k, v in self.tables.items()},
                "columns": {k: v.model_dump(mode="json") for k, v in self.columns.items()},
                "audit_log": [r.model_dump(mode="json") for r in self.audit_log],
                "lineage_graph": self.lineage_graph,
                "resolved_aliases": getattr(semantic_engine, "resolved_aliases", {})
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _load_persisted_state(self) -> bool:
        """Loads state from disk if available."""
        if not STATE_FILE.exists():
            return False
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.tables = {k: AtlanTable(**v) for k, v in state.get("tables", {}).items()}
            self.columns = {k: AtlanColumn(**v) for k, v in state.get("columns", {}).items()}
            self.audit_log = [AtlanAuditRecord(**r) for r in state.get("audit_log", [])]
            self.lineage_graph = state.get("lineage_graph", {})
            
            from semantics.engine import semantic_engine
            if "resolved_aliases" in state:
                semantic_engine.resolved_aliases = state["resolved_aliases"]
            return True
        except Exception:
            return False


    def reset_catalog(self):
        """Resets catalog to initial state with deliberate anomalies."""
        self.tables = {}
        self.columns = {}
        self.audit_log = []
        self.lineage_graph = {}
        try:
            from semantics.engine import semantic_engine
            semantic_engine.resolved_aliases = {}
        except Exception:
            pass
        self._seed_sample_catalog()
        self._save_persisted_state()

    def _seed_sample_catalog(self):
        """Populates the catalog with typical enterprise tables containing governance gaps."""
        # 1. Customer Dimension (Contains untagged PII & PCI)
        dim_cust_guid = "table-dim-cust-001"
        cust_cols = [
            AtlanColumn(
                guid="col-cust-001",
                name="customer_id",
                qualified_name="analytics.core.dim_customers.customer_id",
                data_type="INT",
                description="Unique identifier for customer.",
                classifications=["Internal"],
                glossary_terms=["Customer Identifier"],
                is_masked=False,
                table_guid=dim_cust_guid
            ),
            AtlanColumn(
                guid="col-cust-002",
                name="user_email",
                qualified_name="analytics.core.dim_customers.user_email",
                data_type="VARCHAR",
                description=None,  # ANOMALY: Missing description
                classifications=[],  # ANOMALY: Missing PII classification
                glossary_terms=[],
                is_masked=False,
                table_guid=dim_cust_guid
            ),
            AtlanColumn(
                guid="col-cust-003",
                name="tax_ssn",
                qualified_name="analytics.core.dim_customers.tax_ssn",
                data_type="VARCHAR",
                description=None,  # ANOMALY
                classifications=[],  # ANOMALY: Missing High-Risk PII
                glossary_terms=[],
                is_masked=False,
                table_guid=dim_cust_guid
            ),
            AtlanColumn(
                guid="col-cust-004",
                name="raw_credit_card",
                qualified_name="analytics.core.dim_customers.raw_credit_card",
                data_type="VARCHAR",
                description=None,  # ANOMALY
                classifications=[],  # ANOMALY: Missing PCI classification
                glossary_terms=[],
                is_masked=False,
                table_guid=dim_cust_guid
            )
        ]
        self.tables[dim_cust_guid] = AtlanTable(
            guid=dim_cust_guid,
            name="dim_customers",
            qualified_name="analytics.core.dim_customers",
            database_name="ANALYTICS",
            schema_name="CORE",
            description="Core customer dimension table.",
            owner="data-team@company.com",
            columns=cust_cols,
            row_count=150000,
            certificate_status="VERIFIED"
        )
        for c in cust_cols:
            self.columns[c.guid] = c

        # 2. Orders Fact (Contains Schema & Semantic Metric Drift)
        fct_orders_guid = "table-fct-orders-002"
        order_cols = [
            AtlanColumn(
                guid="col-ord-001",
                name="order_id",
                qualified_name="finance.public.fct_orders.order_id",
                data_type="INT",
                description="Unique order number.",
                classifications=["Internal"],
                glossary_terms=[],
                is_masked=False,
                table_guid=fct_orders_guid
            ),
            AtlanColumn(
                guid="col-ord-002",
                name="gross_rev",  # ANOMALY: Renamed from expected 'order_total', breaking ARR metric
                qualified_name="finance.public.fct_orders.gross_rev",
                data_type="FLOAT",
                description=None,  # ANOMALY
                classifications=[],
                glossary_terms=[],
                is_masked=False,
                table_guid=fct_orders_guid
            ),
            AtlanColumn(
                guid="col-ord-003",
                name="is_recurring",
                qualified_name="finance.public.fct_orders.is_recurring",
                data_type="BOOLEAN",
                description="Flag indicating if the order is an ongoing subscription.",
                classifications=["Internal"],
                glossary_terms=[],
                is_masked=False,
                table_guid=fct_orders_guid
            )
        ]
        self.tables[fct_orders_guid] = AtlanTable(
            guid=fct_orders_guid,
            name="fct_orders",
            qualified_name="finance.public.fct_orders",
            database_name="FINANCE",
            schema_name="PUBLIC",
            description=None,  # ANOMALY: Missing table description
            owner=None,        # ANOMALY: Missing owner
            columns=order_cols,
            row_count=820000,
            certificate_status="DRAFT"
        )
        for c in order_cols:
            self.columns[c.guid] = c

        # 3. Marketing Leads (Untagged contact info)
        mkt_leads_guid = "table-mkt-leads-003"
        leads_cols = [
            AtlanColumn(
                guid="col-lead-001",
                name="lead_id",
                qualified_name="marketing.campaigns.leads.lead_id",
                data_type="INT",
                description="Lead tracking ID",
                classifications=["Internal"],
                glossary_terms=[],
                is_masked=False,
                table_guid=mkt_leads_guid
            ),
            AtlanColumn(
                guid="col-lead-002",
                name="phone_number",
                qualified_name="marketing.campaigns.leads.phone_number",
                data_type="VARCHAR",
                description=None,  # ANOMALY
                classifications=[],  # ANOMALY: Untagged PII
                glossary_terms=[],
                is_masked=False,
                table_guid=mkt_leads_guid
            )
        ]
        self.tables[mkt_leads_guid] = AtlanTable(
            guid=mkt_leads_guid,
            name="leads",
            qualified_name="marketing.campaigns.leads",
            database_name="MARKETING",
            schema_name="CAMPAIGNS",
            description="Campaign lead acquisition data.",
            owner="growth-team@company.com",
            columns=leads_cols,
            row_count=45000,
            certificate_status="VERIFIED"
        )
        for c in leads_cols:
            self.columns[c.guid] = c

        # Lineage: dim_customers & fct_orders -> executive_arr_dashboard
        self.lineage_graph[dim_cust_guid] = ["dash-exec-arr-001"]
        self.lineage_graph[fct_orders_guid] = ["dash-exec-arr-001"]

    def list_tables(self) -> List[AtlanTable]:
        # Sync column states into table column lists
        for t in self.tables.values():
            t.columns = [self.columns[c.guid] for c in t.columns if c.guid in self.columns]
        return list(self.tables.values())

    def get_table(self, guid: str) -> Optional[AtlanTable]:
        t = self.tables.get(guid)
        if t:
            t.columns = [self.columns[c.guid] for c in t.columns if c.guid in self.columns]
        return t

    def get_column(self, guid: str) -> Optional[AtlanColumn]:
        return self.columns.get(guid)

    def search_assets(self, query: str) -> List[Dict[str, Any]]:
        results = []
        q = query.lower()
        for t in self.tables.values():
            if q in t.name.lower() or q in t.qualified_name.lower():
                results.append({"guid": t.guid, "type": "Table", "name": t.name, "qualified_name": t.qualified_name})
        for c in self.columns.values():
            if q in c.name.lower() or q in c.qualified_name.lower():
                results.append({"guid": c.guid, "type": "Column", "name": c.name, "qualified_name": c.qualified_name})
        return results

    def apply_classification(self, column_guid: str, classification_name: str, actor: str = "Agno:PIISecurityHealer", reason: str = "Auto-healed by Agno Agent") -> bool:
        col = self.columns.get(column_guid)
        if not col:
            return False

        prev = {"classifications": list(col.classifications), "is_masked": col.is_masked}
        if classification_name not in col.classifications:
            col.classifications.append(classification_name)
        
        # Mask if sensitive
        if classification_name in ["PII", "PCI", "HighRisk:Restricted", "FINANCIAL"]:
            col.is_masked = True

        new = {"classifications": list(col.classifications), "is_masked": col.is_masked}

        # Sync back to parent table if present
        tbl = self.tables.get(col.table_guid)
        if tbl:
            tbl.columns = [col if c.guid == col.guid else c for c in tbl.columns]

        # Record audit
        self.audit_log.append(AtlanAuditRecord(
            id=str(uuid.uuid4()),
            action=f"APPLY_CLASSIFICATION: {classification_name}",
            asset_guid=col.guid,
            asset_name=col.qualified_name,
            actor=actor,
            reason=reason,
            previous_state=prev,
            new_state=new
        ))
        self._save_persisted_state()
        return True


    def update_description(self, guid: str, description: str, is_table: bool = False, actor: str = "Agno:MetadataEnricher", reason: str = "Auto-generated metadata") -> bool:
        target = self.tables.get(guid) if is_table else self.columns.get(guid)
        if not target:
            return False

        prev = {"description": target.description}
        target.description = description
        new = {"description": target.description}

        if not is_table:
            col = self.columns.get(guid)
            if col:
                tbl = self.tables.get(col.table_guid)
                if tbl:
                    tbl.columns = [col if c.guid == col.guid else c for c in tbl.columns]

        self.audit_log.append(AtlanAuditRecord(
            id=str(uuid.uuid4()),
            action="UPDATE_DESCRIPTION",
            asset_guid=guid,
            asset_name=target.qualified_name,
            actor=actor,
            reason=reason,
            previous_state=prev,
            new_state=new
        ))
        self._save_persisted_state()
        return True

    def link_glossary_term(self, guid: str, term_name: str, is_table: bool = False, actor: str = "Agno:MetadataEnricher") -> bool:
        target = self.tables.get(guid) if is_table else self.columns.get(guid)
        if not target:
            return False

        prev = {"glossary_terms": list(target.glossary_terms)}
        if term_name not in target.glossary_terms:
            target.glossary_terms.append(term_name)
        new = {"glossary_terms": list(target.glossary_terms)}

        if not is_table:
            col = self.columns.get(guid)
            if col:
                tbl = self.tables.get(col.table_guid)
                if tbl:
                    tbl.columns = [col if c.guid == col.guid else c for c in tbl.columns]

        self.audit_log.append(AtlanAuditRecord(
            id=str(uuid.uuid4()),
            action=f"LINK_GLOSSARY_TERM: {term_name}",
            asset_guid=guid,
            asset_name=target.qualified_name,
            actor=actor,
            reason="Associated business glossary term via Semantic Engine match",
            previous_state=prev,
            new_state=new
        ))
        self._save_persisted_state()
        return True


    def set_owner(self, table_guid: str, owner: str, actor: str = "Agno:GovernanceOrchestrator") -> bool:
        table = self.tables.get(table_guid)
        if not table:
            return False
        prev = {"owner": table.owner}
        table.owner = owner
        new = {"owner": table.owner}
        self.audit_log.append(AtlanAuditRecord(
            id=str(uuid.uuid4()),
            action=f"ASSIGN_OWNER: {owner}",
            asset_guid=table.guid,
            asset_name=table.qualified_name,
            actor=actor,
            reason="Assigned default steward based on domain schema",
            previous_state=prev,
            new_state=new
        ))
        self._save_persisted_state()
        return True

    def get_audit_trail(self) -> List[AtlanAuditRecord]:
        return self.audit_log

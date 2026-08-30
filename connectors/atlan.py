from typing import Dict, Any, List, Optional
from atlan_integration.client import atlan_client
from .base import BaseConnector, ConnectorType, TableSchema, ColumnSchema


class AtlanConnector(BaseConnector):
    """
    Modular Active Metadata Connector for Atlan Platform.
    Provides catalog metadata, classifications, and audit logs.
    """

    def __init__(self):
        super().__init__(name="Atlan-Active-Catalog-Adapter", connector_type=ConnectorType.CATALOG)

    def connect(self) -> bool:
        return True

    def list_tables(self) -> List[TableSchema]:
        atlan_tables = atlan_client.list_tables()
        schemas = []
        for tbl in atlan_tables:
            columns = [
                ColumnSchema(
                    name=c.name,
                    guid=c.guid,
                    data_type=c.data_type,
                    is_nullable=getattr(c, "is_nullable", True),
                    description=c.description,
                    classifications=c.classifications,
                    is_masked=c.is_masked
                ) for c in tbl.columns
            ]
            schemas.append(TableSchema(
                name=tbl.name,
                qualified_name=tbl.qualified_name,
                connector_type=ConnectorType.CATALOG,
                guid=tbl.guid,
                description=tbl.description,
                owner=tbl.owner,
                columns=columns,
                row_count=tbl.row_count
            ))
        return schemas

    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        tables = self.list_tables()
        return next((t for t in tables if t.name == table_name), None)

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return atlan_client.search_assets(query)

    def apply_data_masking(self, table_name: str, column_name: str, mask_type: str = "MASK_ALL") -> bool:
        tbl = self.get_table_schema(table_name)
        if tbl:
            col = next((c for c in tbl.columns if c.name == column_name), None)
            if col:
                return atlan_client.apply_classification(col.name, "RESTRICTED", reason="Enforcing masking via Atlan connector")
        return False

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from .base import BaseConnector, ConnectorType, TableSchema, ColumnSchema


class NoSQLConnector(BaseConnector):
    """
    Modular NoSQL Database Connector (MongoDB / JSON Document Store).
    Manages document collections (customer_profiles, event_logs).
    """

    def __init__(self, storage_path: Optional[str] = None):
        super().__init__(name="MongoDB-NoSQL-Adapter", connector_type=ConnectorType.NOSQL)
        self.storage_path = Path(storage_path or Path(__file__).parent.parent / "nosql_store.json")
        self._masked_fields = set()
        self._init_documents()

    def _init_documents(self):
        if not self.storage_path.exists():
            default_data = {
                "customer_profiles": [
                    {
                        "_id": "doc_cust_001",
                        "user_id": "USR-8801",
                        "profile": {
                            "legal_name": "Eleanor Vance",
                            "contact_email": "eleanor.vance@hillhouse.com",
                            "mobile_phone": "+1-555-019-2834",
                            "ssn": "888-12-3456"
                        },
                        "preferences": {"notifications": True, "currency": "USD"},
                        "tier": "PLATINUM"
                    },
                    {
                        "_id": "doc_cust_002",
                        "user_id": "USR-8802",
                        "profile": {
                            "legal_name": "Theodora Crain",
                            "contact_email": "theo.crain@design.co",
                            "mobile_phone": "+1-555-014-9988",
                            "ssn": "777-23-4567"
                        },
                        "preferences": {"notifications": False, "currency": "EUR"},
                        "tier": "GOLD"
                    }
                ],
                "event_logs": [
                    {"_id": "evt_101", "event_name": "USER_CHECKOUT", "user_id": "USR-8801", "amount": 340.00, "timestamp": "2026-08-27T10:00:00Z"},
                    {"_id": "evt_102", "event_name": "PROFILE_UPDATE", "user_id": "USR-8802", "amount": 0.00, "timestamp": "2026-08-27T11:15:00Z"}
                ]
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2)

    def _read_data(self) -> Dict[str, Any]:
        if self.storage_path.exists():
            with open(self.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def connect(self) -> bool:
        return True

    def list_tables(self) -> List[TableSchema]:
        data = self._read_data()
        tables = []
        for coll_name, docs in data.items():
            tables.append(self.get_table_schema(coll_name))
        return [t for t in tables if t]

    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        data = self._read_data()
        docs = data.get(table_name, [])
        if not docs:
            return None

        # Infer columns from document keys
        sample_doc = docs[0]
        columns = []
        for k, v in sample_doc.items():
            dtype = "DOCUMENT" if isinstance(v, dict) else type(v).__name__.upper()
            columns.append(ColumnSchema(
                name=k,
                data_type=dtype,
                is_masked=f"{table_name}.{k}" in self._masked_fields
            ))
            # Flatten 1 level of nested profile keys
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    columns.append(ColumnSchema(
                        name=f"{k}.{sub_k}",
                        data_type=type(sub_v).__name__.upper(),
                        is_masked=f"{table_name}.{k}.{sub_k}" in self._masked_fields
                    ))

        return TableSchema(
            name=table_name,
            qualified_name=f"mongodb.cluster0.{table_name}",
            connector_type=ConnectorType.NOSQL,
            description=f"MongoDB NoSQL Collection '{table_name}' storing dynamic JSON documents.",
            columns=columns,
            row_count=len(docs)
        )

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        # Simple collection fetch or filter
        data = self._read_data()
        coll = data.get(query, [])
        return coll

    def apply_data_masking(self, table_name: str, column_name: str, mask_type: str = "MASK_ALL") -> bool:
        self._masked_fields.add(f"{table_name}.{column_name}")
        return True

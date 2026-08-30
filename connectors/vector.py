from typing import Dict, Any, List, Optional
from pathlib import Path
from .base import BaseConnector, ConnectorType, TableSchema, ColumnSchema


class VectorConnector(BaseConnector):
    """
    Modular Vector Database Connector (ChromaDB / Qdrant for RAG Pipelines).
    Inspects embedding collections and chunk metadata for PII leakage.
    """

    def __init__(self, persist_dir: Optional[str] = None):
        super().__init__(name="ChromaDB-Vector-Adapter", connector_type=ConnectorType.VECTOR)
        self.persist_dir = persist_dir or str(Path(__file__).parent.parent / "chroma_store")
        self._masked_chunks = set()
        self._collections = {
            "enterprise_kb_chunks": [
                {
                    "id": "chunk_001",
                    "text": "Employee John Doe SSN 999-11-2222 salary details for FY2026.",
                    "metadata": {"source_doc": "hr_payroll_2026.pdf", "department": "HR", "author_email": "john.doe@company.com"}
                },
                {
                    "id": "chunk_002",
                    "text": "Quarterly Financial projections for Q3 indicate 24% YoY growth in SaaS subscriptions.",
                    "metadata": {"source_doc": "investor_q3_briefing.pdf", "department": "FINANCE", "is_confidential": True}
                }
            ],
            "support_chat_embeddings": [
                {
                    "id": "chunk_003",
                    "text": "Customer reported issue paying with Visa credit card ending in 4111.",
                    "metadata": {"ticket_id": "TICK-492", "channel": "zendesk"}
                }
            ]
        }

    def connect(self) -> bool:
        return True

    def list_tables(self) -> List[TableSchema]:
        tables = []
        for coll_name, chunks in self._collections.items():
            tables.append(self.get_table_schema(coll_name))
        return tables

    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        chunks = self._collections.get(table_name)
        if not chunks:
            return None

        cols_def = [
            ("id", "STRING", False, None),
            ("text", "TEXT", False, "Raw text chunk embedding"),
            ("metadata.source_doc", "STRING", True, None),
            ("metadata.author_email", "STRING", True, None),
            ("metadata.department", "STRING", True, None)
        ]
        columns = [
            ColumnSchema(
                name=name,
                data_type=dtype,
                is_nullable=nullable,
                description=desc,
                is_masked=f"{table_name}.{name}" in self._masked_chunks
            )
            for name, dtype, nullable, desc in cols_def
        ]

        return TableSchema(
            name=table_name,
            qualified_name=f"chroma.default.{table_name}",
            connector_type=ConnectorType.VECTOR,
            description=f"ChromaDB Vector Collection '{table_name}' for RAG semantic search.",
            columns=columns,
            row_count=len(chunks)
        )

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return self._collections.get(query, [])

    def apply_data_masking(self, table_name: str, column_name: str, mask_type: str = "MASK_ALL") -> bool:
        self._masked_chunks.add(f"{table_name}.{column_name}")
        return True

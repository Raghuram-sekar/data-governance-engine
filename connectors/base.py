from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class ConnectorType(str, Enum):
    RELATIONAL = "RELATIONAL"
    NOSQL = "NOSQL"
    VECTOR = "VECTOR"
    CATALOG = "CATALOG"
    FILESYSTEM = "FILESYSTEM"


class ColumnSchema(BaseModel):
    name: str
    data_type: str
    guid: Optional[str] = None
    is_nullable: bool = True
    description: Optional[str] = None
    classifications: List[str] = Field(default_factory=list)
    is_masked: bool = False


class TableSchema(BaseModel):
    name: str
    qualified_name: str
    connector_type: ConnectorType
    guid: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    columns: List[ColumnSchema] = Field(default_factory=list)
    row_count: int = 0


class BaseConnector(ABC):
    """Abstract Base Class for all modular database & storage connectors."""

    def __init__(self, name: str, connector_type: ConnectorType):
        self.name = name
        self.connector_type = connector_type

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to data store."""
        pass

    @abstractmethod
    def list_tables(self) -> List[TableSchema]:
        """List all tables/collections/indices in the data store."""
        pass

    @abstractmethod
    def get_table_schema(self, table_name: str) -> Optional[TableSchema]:
        """Fetch schema for a specific table/collection."""
        pass

    @abstractmethod
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a query or filtered scan."""
        pass

    @abstractmethod
    def apply_data_masking(self, table_name: str, column_name: str, mask_type: str) -> bool:
        """Enforce data masking on a sensitive field."""
        pass

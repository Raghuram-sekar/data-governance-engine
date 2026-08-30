from typing import Dict, List, Optional
from .base import BaseConnector, ConnectorType, TableSchema, ColumnSchema
from .relational import RelationalConnector
from .nosql import NoSQLConnector
from .vector import VectorConnector
from .atlan import AtlanConnector


class ConnectorRegistry:
    """Central registry of active multi-database connectors."""

    def __init__(self):
        self._connectors: Dict[str, BaseConnector] = {}
        self._init_defaults()

    def _init_defaults(self):
        self.register("atlan", AtlanConnector())
        self.register("postgres", RelationalConnector())
        self.register("mongodb", NoSQLConnector())
        self.register("chroma", VectorConnector())

    def register(self, key: str, connector: BaseConnector):
        self._connectors[key.lower()] = connector

    def get(self, key: str) -> Optional[BaseConnector]:
        return self._connectors.get(key.lower())

    def list_all(self) -> Dict[str, BaseConnector]:
        return self._connectors


connector_registry = ConnectorRegistry()

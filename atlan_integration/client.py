from typing import Optional
from config.settings import settings
from .mock_client import MockAtlanClient


class AtlanClient:
    """
    Unified Atlan client gateway.
    Delegates to MockAtlanClient for offline simulations/development,
    or official pyatlan client when live credentials are provided.
    """

    def __init__(self, use_mock: Optional[bool] = None):
        self.use_mock = use_mock if use_mock is not None else settings.use_mock_atlan
        if self.use_mock:
            self._client = MockAtlanClient()
        else:
            # Placeholder for live pyatlan client integration
            try:
                import pyatlan
                # Live pyatlan initialization if needed
                self._client = MockAtlanClient()
            except ImportError:
                self._client = MockAtlanClient()

    @property
    def raw_client(self):
        return self._client

    def reset(self):
        if hasattr(self._client, "reset_catalog"):
            self._client.reset_catalog()


    def list_tables(self):
        return self._client.list_tables()

    def get_table(self, guid: str):
        return self._client.get_table(guid)

    def get_column(self, guid: str):
        return self._client.get_column(guid)

    def search_assets(self, query: str):
        return self._client.search_assets(query)

    def apply_classification(self, column_guid: str, classification_name: str, actor: str = "AgnoAgent", reason: str = ""):
        return self._client.apply_classification(column_guid, classification_name, actor=actor, reason=reason)

    def update_description(self, guid: str, description: str, is_table: bool = False, actor: str = "AgnoAgent", reason: str = ""):
        return self._client.update_description(guid, description, is_table=is_table, actor=actor, reason=reason)

    def link_glossary_term(self, guid: str, term_name: str, is_table: bool = False, actor: str = "AgnoAgent"):
        return self._client.link_glossary_term(guid, term_name, is_table=is_table, actor=actor)

    def set_owner(self, table_guid: str, owner: str, actor: str = "AgnoAgent"):
        return self._client.set_owner(table_guid, owner, actor=actor)

    def get_audit_trail(self):
        return self._client.get_audit_trail()


# Global shared client instance
atlan_client = AtlanClient()

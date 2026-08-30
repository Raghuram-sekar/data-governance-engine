from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlanAssetType(str, Enum):
    DATABASE = "Database"
    SCHEMA = "Schema"
    TABLE = "Table"
    VIEW = "View"
    COLUMN = "Column"
    GLOSSARY_TERM = "AtlasGlossaryTerm"


class AnomalyType(str, Enum):
    UNCLASSIFIED_PII = "UNCLASSIFIED_PII"
    MISSING_DESCRIPTION = "MISSING_DESCRIPTION"
    UNLINKED_GLOSSARY = "UNLINKED_GLOSSARY"
    MISSING_OWNER = "MISSING_OWNER"
    SEMANTIC_METRIC_DRIFT = "SEMANTIC_METRIC_DRIFT"
    BROKEN_LINEAGE = "BROKEN_LINEAGE"


class AtlanColumn(BaseModel):
    guid: str
    name: str
    qualified_name: str
    data_type: str = "VARCHAR"
    description: Optional[str] = None
    classifications: List[str] = Field(default_factory=list)
    glossary_terms: List[str] = Field(default_factory=list)
    is_masked: bool = False
    table_guid: str


class AtlanTable(BaseModel):
    guid: str
    name: str
    qualified_name: str
    database_name: str
    schema_name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    columns: List[AtlanColumn] = Field(default_factory=list)
    row_count: int = 0
    certificate_status: Optional[str] = None  # "VERIFIED", "DRAFT", "DEPRECATED"
    glossary_terms: List[str] = Field(default_factory=list)


class GovernanceAnomaly(BaseModel):
    id: str
    anomaly_type: AnomalyType
    asset_guid: str
    asset_name: str
    asset_type: AtlanAssetType
    details: str
    severity: str  # "HIGH", "MEDIUM", "LOW"
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    suggested_action: str
    is_resolved: bool = False


class AtlanAuditRecord(BaseModel):
    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: str
    asset_guid: str
    asset_name: str
    actor: str
    reason: str
    previous_state: Dict[str, Any] = Field(default_factory=dict)
    new_state: Dict[str, Any] = Field(default_factory=dict)


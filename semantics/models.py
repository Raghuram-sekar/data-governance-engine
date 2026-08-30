from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SensitivityLevel(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    PII = "PII"          # Personally Identifiable Information
    PCI = "PCI"          # Payment Card Information
    HIPAA = "HIPAA"      # Health Information
    FINANCIAL = "FINANCIAL"


class GlossaryTerm(BaseModel):
    name: str
    definition: str
    domain: str
    synonyms: List[str] = Field(default_factory=list)
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    required_tags: List[str] = Field(default_factory=list)
    related_metrics: List[str] = Field(default_factory=list)


class ClassificationRule(BaseModel):
    rule_id: str
    pattern: str  # Regex pattern for column name or content
    classification: SensitivityLevel
    confidence: float
    description: str
    masking_strategy: Optional[str] = None  # e.g., "MASK_ALL", "MASK_EMAIL", "HASH"


class MetricDefinition(BaseModel):
    name: str
    display_name: str
    description: str
    business_unit: str
    formula: str
    expected_source_entities: List[str]
    expected_columns: List[str]


class SemanticOntology(BaseModel):
    version: str
    domain: str
    glossary_terms: List[GlossaryTerm]
    classification_rules: List[ClassificationRule]
    metrics: List[MetricDefinition]

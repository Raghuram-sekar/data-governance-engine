import json
import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from .models import SemanticOntology, GlossaryTerm, ClassificationRule, MetricDefinition, SensitivityLevel


class SemanticEngine:
    """
    The Semantic Engine provides business domain intelligence, standard definitions,
    sensitivity classification rules, and metric specifications.
    """

    def __init__(self, ontology_path: Optional[str] = None):
        if ontology_path is None:
            ontology_path = str(Path(__file__).parent / "ontology.json")
        
        self.ontology_path = ontology_path
        self.ontology: SemanticOntology = self._load_ontology(ontology_path)
        self.resolved_aliases: Dict[str, Dict[str, str]] = {}  # metric_name -> {expected_col: actual_col}

    def _load_ontology(self, path: str) -> SemanticOntology:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SemanticOntology(**data)

    def lookup_glossary_term(self, name_or_synonym: str) -> Optional[GlossaryTerm]:
        """Finds the canonical glossary term by name or known synonyms."""
        query = name_or_synonym.strip().lower()
        for term in self.ontology.glossary_terms:
            if term.name.lower() == query:
                return term
            for syn in term.synonyms:
                if syn.lower() == query or query in syn.lower() or syn.lower() in query:
                    return term
        return None

    def match_sensitivity(self, column_name: str, data_type: str = "VARCHAR") -> Optional[Tuple[ClassificationRule, float]]:
        """
        Evaluates column name and type against semantic classification rules.
        Returns the best matching rule and its confidence score.
        """
        best_match: Optional[Tuple[ClassificationRule, float]] = None
        highest_conf = 0.0

        for rule in self.ontology.classification_rules:
            if re.search(rule.pattern, column_name):
                if rule.confidence > highest_conf:
                    highest_conf = rule.confidence
                    best_match = (rule, rule.confidence)

        return best_match

    def get_metric_definition(self, metric_name: str) -> Optional[MetricDefinition]:
        """Fetches metric definition and expected column bindings."""
        query = metric_name.strip().lower()
        for m in self.ontology.metrics:
            if m.name.lower() == query or m.display_name.lower() == query:
                return m
        return None

    def register_metric_alias(self, metric_name: str, expected_col: str, actual_col: str):
        """Registers a healed alias mapping for a metric."""
        m_key = metric_name.lower()
        if m_key not in self.resolved_aliases:
            self.resolved_aliases[m_key] = {}
        self.resolved_aliases[m_key][expected_col.lower()] = actual_col.lower()

    def check_metric_health(self, metric_name: str, available_columns: List[str]) -> Dict[str, Any]:
        """
        Validates if an asset provides the expected semantic columns for a metric.
        Detects missing or renamed columns (schema/semantic drift).
        """
        metric = self.get_metric_definition(metric_name)
        if not metric:
            return {"status": "UNKNOWN_METRIC", "metric": metric_name}

        available_lower = [c.lower() for c in available_columns]
        m_aliases = self.resolved_aliases.get(metric_name.lower(), {})
        missing_cols = []
        renamed_suggestions = {}

        for expected in metric.expected_columns:
            exp_low = expected.lower()
            # If present directly or has a resolved alias present
            if exp_low in available_lower or (exp_low in m_aliases and m_aliases[exp_low] in available_lower):
                continue

            missing_cols.append(expected)
            # Check for semantic synonym match in available columns
            term = self.lookup_glossary_term(expected)
            if term:
                for actual_col in available_columns:
                    if any(s.lower() in actual_col.lower() for s in term.synonyms):
                        renamed_suggestions[expected] = actual_col

        is_healthy = len(missing_cols) == 0
        return {
            "metric": metric.display_name,
            "is_healthy": is_healthy,
            "missing_columns": missing_cols,
            "suggested_mappings": renamed_suggestions,
            "formula": metric.formula
        }

    def list_all_glossary_terms(self) -> List[GlossaryTerm]:
        return self.ontology.glossary_terms


# Singleton default instance
semantic_engine = SemanticEngine()

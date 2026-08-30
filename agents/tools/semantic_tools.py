from typing import List, Dict, Any, Optional
import json
from semantics.engine import semantic_engine


def lookup_semantic_glossary_term(term_name_or_synonym: Optional[str] = "", **kwargs) -> str:
    """
    Search the semantic ontology for official business definitions, domain, and sensitivity of a term.
    
    Args:
        term_name_or_synonym: Term or column name to match (e.g. 'user_email', 'arr', 'ssn')
    """
    query = term_name_or_synonym or kwargs.get("term_name") or kwargs.get("term") or kwargs.get("query") or kwargs.get("column_name") or ""
    term = semantic_engine.lookup_glossary_term(query)
    if not term:
        return json.dumps({"found": False, "query": query})
    return json.dumps({"found": True, "term": term.model_dump()}, indent=2)


def evaluate_column_sensitivity(column_name: Optional[str] = "", data_type: Optional[str] = "VARCHAR", **kwargs) -> str:
    """
    Evaluate a column name and type against semantic classification rules to detect sensitive data (PII, PCI, HIPAA).
    
    Args:
        column_name: Name of the column
        data_type: SQL data type (e.g. VARCHAR, INT)
    """
    col = column_name or kwargs.get("name") or kwargs.get("col") or ""
    dtype = data_type or kwargs.get("type") or "VARCHAR"
    match = semantic_engine.match_sensitivity(col, dtype)
    if not match:
        return json.dumps({
            "is_sensitive": False,
            "column_name": col,
            "classification": "INTERNAL",
            "confidence": 1.0
        })
    
    rule, conf = match
    return json.dumps({
        "is_sensitive": True,
        "column_name": col,
        "classification": rule.classification.value,
        "confidence": conf,
        "rule_id": rule.rule_id,
        "masking_strategy": rule.masking_strategy,
        "description": rule.description
    }, indent=2)


def validate_metric_semantic_health(metric_name: Optional[str] = "annual_recurring_revenue", available_columns_json: Optional[str] = "[]", **kwargs) -> str:
    """
    Check if a table or query has all required columns for a semantic metric, or if drift/renaming occurred.
    
    Args:
        metric_name: Name of the metric (e.g., 'annual_recurring_revenue')
        available_columns_json: JSON list of actual column names in the table
    """
    m_name = metric_name or kwargs.get("metric") or "annual_recurring_revenue"
    raw_cols = available_columns_json or kwargs.get("columns") or "[]"
    if isinstance(raw_cols, list):
        cols = raw_cols
    else:
        try:
            cols = json.loads(str(raw_cols))
        except Exception:
            cols = [c.strip() for c in str(raw_cols).split(",") if c.strip()]
        
    result = semantic_engine.check_metric_health(m_name, cols)
    return json.dumps(result, indent=2)


def list_available_semantic_terms(**kwargs) -> str:
    """
    List all official business glossary terms available in the semantic ontology.
    """
    terms = [t.model_dump() for t in semantic_engine.list_all_glossary_terms()]
    return json.dumps(terms, indent=2)

from typing import Dict, Any, List, Optional
import json
from atlan_integration.client import atlan_client


def search_atlan_assets(query: Optional[str] = "", **kwargs) -> str:
    """
    Search assets (tables, columns, schemas) in the Atlan active metadata catalog.
    
    Args:
        query: Search keyword (e.g. 'customer', 'email', 'orders')
    """
    q = query or kwargs.get("search") or kwargs.get("keyword") or ""
    results = atlan_client.search_assets(q)
    return json.dumps(results, indent=2)


def get_atlan_table_details(table_guid: Optional[str] = "", **kwargs) -> str:
    """
    Retrieve full metadata, schema, owner, and column details for a given table GUID from Atlan.
    
    Args:
        table_guid: Unique identifier of the table
    """
    guid = table_guid or kwargs.get("guid") or kwargs.get("table_id") or ""
    table = atlan_client.get_table(guid)
    if not table:
        return json.dumps({"error": f"Table with GUID '{guid}' not found"})
    return json.dumps(table.model_dump(), indent=2)


def get_atlan_column_details(column_guid: Optional[str] = "", **kwargs) -> str:
    """
    Retrieve column metadata, current classifications, and glossary bindings from Atlan.
    
    Args:
        column_guid: Unique identifier of the column
    """
    guid = column_guid or kwargs.get("guid") or kwargs.get("column_id") or ""
    col = atlan_client.get_column(guid)
    if not col:
        return json.dumps({"error": f"Column with GUID '{guid}' not found"})
    return json.dumps(col.model_dump(), indent=2)


def apply_atlan_classification(column_guid: Optional[str] = "", classification_name: Optional[str] = "", reason: Optional[str] = "Automated AI classification", **kwargs) -> str:
    """
    Apply a security classification (e.g., PII, PCI, HighRisk:Restricted) to a column in Atlan.
    This triggers automatic masking and policy enforcement.
    
    Args:
        column_guid: Unique identifier of the column
        classification_name: Name of classification tag (e.g., 'PII', 'PCI')
        reason: Explanation of why this classification is applied
    """
    guid = column_guid or kwargs.get("guid") or kwargs.get("column_id") or ""
    cls_name = classification_name or kwargs.get("classification") or kwargs.get("tag") or "PII"
    rsn = reason or kwargs.get("description") or "Automated classification applied"
    success = atlan_client.apply_classification(guid, cls_name, actor="Agno:PIISecurityHealer", reason=rsn)
    return json.dumps({"status": "SUCCESS" if success else "FAILED", "column_guid": guid, "classification": cls_name})


def update_atlan_description(guid: Optional[str] = "", description: Any = "", is_table: Optional[bool] = False, reason: Optional[str] = "AI generated documentation", **kwargs) -> str:
    """
    Update the business description for a table or column in Atlan.
    
    Args:
        guid: Unique identifier of the asset
        description: High quality business description
        is_table: True if the asset is a table, False if column
        reason: Reason for update
    """
    target_guid = guid or kwargs.get("table_guid") or kwargs.get("column_guid") or kwargs.get("asset_guid") or ""
    desc_val = description or kwargs.get("text") or kwargs.get("summary") or "Enriched documentation"
    if isinstance(desc_val, dict):
        desc = desc_val.get("definition") or desc_val.get("description") or str(desc_val)
    else:
        desc = str(desc_val)
    is_tbl = bool(is_table) if is_table is not None else kwargs.get("is_tbl", False)
    rsn = reason or kwargs.get("explanation") or "AI generated documentation"
    success = atlan_client.update_description(target_guid, desc, is_table=is_tbl, actor="Agno:MetadataEnricher", reason=rsn)
    return json.dumps({"status": "SUCCESS" if success else "FAILED", "guid": target_guid, "description": desc})



def link_atlan_glossary_term(guid: Optional[str] = "", term_name: Optional[str] = "", is_table: Optional[bool] = False, **kwargs) -> str:
    """
    Link a verified business glossary term to an asset in Atlan.
    
    Args:
        guid: Unique identifier of the asset
        term_name: Name of the verified glossary term
        is_table: True if target is a table, False if column
    """
    target_guid = guid or kwargs.get("column_guid") or kwargs.get("table_guid") or ""
    term = term_name or kwargs.get("term") or kwargs.get("glossary_term") or ""
    is_tbl = bool(is_table) if is_table is not None else kwargs.get("is_tbl", False)
    success = atlan_client.link_glossary_term(target_guid, term, is_table=is_tbl, actor="Agno:MetadataEnricher")
    return json.dumps({"status": "SUCCESS" if success else "FAILED", "guid": target_guid, "linked_term": term})


def assign_atlan_owner(table_guid: Optional[str] = "", owner_email: Optional[str] = "", **kwargs) -> str:
    """
    Assign a data owner/steward to a table in Atlan.
    
    Args:
        table_guid: Unique identifier of the table
        owner_email: Email or team handle of the owner
    """
    guid = table_guid or kwargs.get("guid") or kwargs.get("table_id") or ""
    owner = owner_email or kwargs.get("email") or kwargs.get("steward") or "data-steward@company.com"
    success = atlan_client.set_owner(guid, owner, actor="Agno:GovernanceOrchestrator")
    return json.dumps({"status": "SUCCESS" if success else "FAILED", "table_guid": guid, "owner": owner})

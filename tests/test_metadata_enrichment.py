from agents.metadata_enricher import MetadataEnricher
from atlan_integration.client import atlan_client


def test_metadata_enricher_table_and_column():
    atlan_client.reset()
    enricher = MetadataEnricher()

    # Enrich table metadata
    tbl_guid = "table-fct-orders-002"
    tbl = atlan_client.get_table(tbl_guid)
    assert tbl.description is None
    assert tbl.owner is None

    res_tbl = enricher.heal_table_metadata(table_guid=tbl_guid, table_name=tbl.name, schema_name=tbl.schema_name)
    assert res_tbl["status"] == "HEALED"
    assert "public-data-steward@company.com" in res_tbl["owner_assigned"]

    # Enrich column metadata
    col_guid = "col-cust-002"  # user_email
    res_col = enricher.heal_column_metadata(column_guid=col_guid, column_name="user_email", table_name="dim_customers")
    assert res_col["status"] == "HEALED"
    assert res_col["glossary_term_linked"] == "Customer Email Address"

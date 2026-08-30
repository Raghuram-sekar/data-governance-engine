from agents.pii_healer import PIISecurityHealer
from atlan_integration.client import atlan_client


def test_pii_security_healer_auto_tagging():
    atlan_client.reset()
    healer = PIISecurityHealer()
    col = atlan_client.get_column("col-cust-002")  # user_email

    assert col is not None
    assert "PII" not in col.classifications

    result = healer.heal_column(column_guid=col.guid, column_name=col.name)
    assert result["status"] == "HEALED"
    assert result["classification_applied"] == "PII"
    assert result["masking_enforced"] is True

    # Verify updated in Atlan client
    updated_col = atlan_client.get_column("col-cust-002")
    assert "PII" in updated_col.classifications
    assert updated_col.is_masked is True

from engine.loop import SelfHealingLoop
from atlan_integration.client import atlan_client


def test_full_self_healing_cycle():
    atlan_client.reset()
    loop = SelfHealingLoop()

    pre_score = loop.calculate_health_score()["overall_score"]
    summary = loop.execute_healing_cycle()

    post_score = summary["post_healing_health"]["overall_score"]
    assert post_score > pre_score

    assert summary["anomalies_detected"] > 0
    assert summary["anomalies_healed"] > 0
    assert summary["total_audit_actions"] > 0

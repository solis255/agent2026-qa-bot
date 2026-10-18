from copy import deepcopy
import pytest
from client_snapshot_helpers import encoded, payload, FIXTURES
from netpilot.client_snapshot.validation import parse_snapshot, SnapshotValidationError


def test_v1_fixtures_and_sanitized_digest():
    value = payload()
    value["client"]["hostname"] = "private-device-name"
    value["adapters"][0]["interface_alias"] = "private-interface-name"
    snapshot, digest = parse_snapshot(encoded(value))
    assert snapshot.client.hostname is None
    assert snapshot.adapters[0].interface_alias is None
    assert snapshot.adapters[0].name == "if-1"
    assert len(digest) == 64
    assert digest == parse_snapshot(encoded(dict(reversed(list(value.items())))))[1]
    assert parse_snapshot(encoded(payload("dns_failure")))[0].checks[0].status == "abnormal"
    with pytest.raises(SnapshotValidationError):
        parse_snapshot((FIXTURES / "client_snapshot_invalid.json").read_bytes())


@pytest.mark.parametrize("mutate", [
    lambda x:x.update(schema_version=2),
    lambda x:x.update(schema_version=True),
    lambda x:x.update(generated_at="2026-01-01T12:00:00"),
    lambda x:x.update(adapters=x["adapters"] * 33),
    lambda x:x.update(dns_servers=["1.1.1.1"] * 17),
    lambda x:x.update(route_summary=x["route_summary"] * 17),
    lambda x:x.update(checks=x["checks"] * 9),
    lambda x:x.update(active_adapter_id="nonexistent"),
    lambda x:x["checks"][0].update(target="metadata.internal"),
    lambda x:x["checks"][3]["result"].update(port=22),
    lambda x:x["checks"][0]["result"].update(addresses=[]),
    lambda x:x["checks"][2]["result"].update(reachable=False),
    lambda x:x["route_summary"][0].update(destination="10.0.0.0/8"),
    lambda x:x["adapters"][0].update(ipv4_addresses=["not-an-ip"]),
    lambda x:x["client"].update(client_instance_id="static-device-id"),
])
def test_strict_bounded_structure(mutate):
    value = payload()
    mutate(value)
    with pytest.raises(SnapshotValidationError):
        parse_snapshot(encoded(value))


def test_missing_gateway_can_be_unknown_not_failed():
    value = payload()
    value["default_gateway"] = None
    value["checks"][2].update(target="unknown", status="error", result={"error_code":"gateway_unknown"})
    snapshot, _ = parse_snapshot(encoded(value))
    assert snapshot.checks[2].result.reachable is None

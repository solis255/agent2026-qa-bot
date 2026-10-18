import pytest
from netpilot.remediation.catalog import CATALOG
from netpilot.remediation.safety import validate_catalog


def test_catalog_covers_p0_categories_and_is_immutable():
    validate_catalog(CATALOG)
    categories={category for template in CATALOG.values() for category in template.issue_types}
    assert {"dns","gateway_connectivity","campus_auth","vpn","proxy","web_only","single_service","unknown"} <= categories
    with pytest.raises(TypeError):CATALOG["injected"]=CATALOG["confirm_scope"]
    assert all(item.risk == "low" and not item.requires_admin for item in CATALOG.values())
    assert all(not item.changes_system_state or item.rollback_instructions for item in CATALOG.values())


def test_static_catalog_has_no_user_or_url_interpolation():
    for item in CATALOG.values():
        assert "{" not in "".join(item.instructions)
        assert "http://" not in "".join(item.instructions)
        assert "https://" not in "".join(item.instructions)

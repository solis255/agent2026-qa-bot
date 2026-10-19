from netpilot.privacy import PrivacyPolicy, redact_mapping, redact_text


def test_default_private_dns_gateway_destination_preserved_public_client_removed():
    value = {"client_ip": "172.23.221.167", "gateway": "172.23.128.1", "dns_servers": ["172.23.0.1", "10.0.0.1"], "destination_ip": "1.1.1.1", "client_public_ip": "8.8.4.4", "port": 443}
    safe = redact_mapping(value).value
    assert safe == {**value, "client_public_ip": "[REDACTED]"}
    # Address removal follows field semantics, even when the values coincide.
    assert redact_mapping({"client_public_ip": "1.1.1.1", "destination_ip": "1.1.1.1"}).value == {
        "client_public_ip": "[REDACTED]", "destination_ip": "1.1.1.1"}


def test_optional_mask_is_deterministic_preserves_special_addresses():
    policy = PrivacyPolicy(mask_private_ip=True)
    value = "172.23.221.167 10.0.0.1 fd00::1234 127.0.0.1 ::1 fe80::1 1.1.1.1"
    safe = redact_text(value, policy).value
    assert "172.23.221.xxx" in safe and "10.0.0.xxx" in safe
    assert "fd00:0000:0000:0000:xxxx:xxxx:xxxx:xxxx" in safe
    assert "127.0.0.1 ::1 fe80::1 1.1.1.1" in safe
    assert redact_text(safe, policy).value == safe


def test_ipv6_urls_preserved_by_default_and_masked_urls_are_valid_and_idempotent():
    value = "[内网](https://[fd00::1234]/help?token=hidden&lang=zh)"
    assert redact_text(value).value == "[内网](https://[fd00::1234]/help?lang=zh)"
    policy = PrivacyPolicy(mask_private_ip=True)
    safe = redact_text(value, policy).value
    assert safe == "[内网](https://[fd00::]/help?lang=zh)"
    assert redact_text(safe, policy).value == safe


def test_mac_detection_does_not_remove_ipv6_segments():
    for address in ["fd00:11:22:33:44:55:66:77", "2001:db8:aa:bb:cc:dd:ee:ff"]:
        assert redact_text(address).value == address
        assert redact_text(f"https://[{address}]/").value == f"https://[{address}]/"

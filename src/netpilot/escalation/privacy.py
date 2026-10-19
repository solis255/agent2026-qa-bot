"""Compatibility facade for the stricter escalation policy; one shared engine."""
from netpilot.privacy import current_policy, redact_text, export_safe

REDACTED_FIELDS = ("hostname", "MAC", "BSSID", "SSID", "password", "cookie", "authorization",
                   "API key", "token", "secret", "credential", "user-agent", "precise_location")


def escalation_policy(policy=None):
    base = current_policy.get()
    return base.model_copy(update={"redact_hostname": True, "redact_mac": True,
        "redact_bssid": True, "redact_ssid": True,
        "mask_private_ip": base.mask_private_ip or bool(policy and policy.mask_private_ip)})


def redact(value, policy=None):
    return None if value is None else redact_text(value, escalation_policy(policy)).value


def safe_package(package):
    return export_safe(package, escalation_policy())

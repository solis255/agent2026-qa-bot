"""Bounded JSON parsing, privacy validation and second-layer sanitization."""

import hashlib
import json
import re

from pydantic import ValidationError
from netpilot.client_snapshot.schemas import ClientDiagnosticSnapshot
from netpilot.privacy.detectors import sensitive_key


class SnapshotValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_SENSITIVE = {"mac", "macaddress", "bssid", "ssid", "password", "cookie", "authorization", "apikey", "token", "secret", "credential", "guid", "pnpdeviceid", "serialnumber", "sid", "productkey", "licensekey"}
_METADATA = {"hostname_redacted", "mac_removed", "ssid_removed", "secrets_removed"}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotValidationError("duplicate_json_keys")
        result[key] = value
    return result


def _scan(value, depth=0):
    if depth > 12:
        raise SnapshotValidationError("nesting_limit")
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
            if key not in _METADATA and (normalized in _SENSITIVE or sensitive_key(key)):
                raise SnapshotValidationError("sensitive_fields")
            _scan(key, depth + 1)
            _scan(child, depth + 1)
    elif isinstance(value, list):
        if len(value) > 32:
            raise SnapshotValidationError("collection_limit")
        for child in value:
            _scan(child, depth + 1)
    elif isinstance(value, str):
        if len(value) > 1024:
            raise SnapshotValidationError("string_limit")
        if "@" in value and re.search(r"[^\s/:]+:[^\s@]+@", value):
            raise SnapshotValidationError("sensitive_values")


def parse_snapshot(raw: bytes, max_bytes: int = 262144) -> tuple[ClientDiagnosticSnapshot, str]:
    if len(raw) > max_bytes:
        raise SnapshotValidationError("file_too_large")
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(SnapshotValidationError("invalid_json")))
    except SnapshotValidationError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise SnapshotValidationError("invalid_json") from exc
    _scan(value)
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise SnapshotValidationError("unsupported_schema")
    try:
        # JSON mode allows ISO datetimes while preserving strict primitive types.
        snapshot = ClientDiagnosticSnapshot.model_validate_json(json.dumps(value))
    except (ValidationError, ValueError) as exc:
        raise SnapshotValidationError("invalid_structure") from exc
    snapshot.client.hostname = None
    id_map = {item.adapter_id: f"if-{index}" for index, item in enumerate(snapshot.adapters, 1)}
    for item in snapshot.adapters:
        item.adapter_id = id_map[item.adapter_id]
        item.name = item.adapter_id
        item.interface_alias = None
    snapshot.active_adapter_id = id_map.get(snapshot.active_adapter_id)
    for item in snapshot.route_summary:
        item.interface_id = id_map.get(item.interface_id)
    for name in type(snapshot.redaction).model_fields:
        setattr(snapshot.redaction, name, True)
    canonical = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return snapshot, hashlib.sha256(canonical.encode("utf-8")).hexdigest()

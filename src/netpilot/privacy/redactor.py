"""Central deterministic safety boundary. No original values leave this module."""
from collections import Counter
import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel

from . import detectors as d
from .ip import CLIENT_PUBLIC_KEYS, IP_PATTERN, mask_address, mask_url_address
from .metadata import metadata_for
from .models import RedactionResult
from .policy import PrivacyPolicy, current_policy
from .url import sanitize_url


class Redactor:
    def __init__(self, policy: PrivacyPolicy | None = None):
        self.policy = policy or current_policy.get()

    def redact(self, value: Any, *, truncate=True, known_context=None) -> RedactionResult:
        counts = Counter()
        warnings = set()
        known = {}
        policy = self.policy

        def category(key):
            key = d.normalize_key(key)
            if d.sensitive_key(key): return "credential", d.REDACTED
            if key in d.HOST_KEYS and policy.redact_hostname: return "hostname", d.HOSTNAME
            if key in d.MAC_KEYS and (policy.redact_bssid if key == "bssid" else policy.redact_mac): return "mac", d.MAC
            if key in d.SSID_KEYS and policy.redact_ssid: return "ssid", d.SSID
            if key in CLIENT_PUBLIC_KEYS and policy.remove_public_ip: return "public_client_ip", d.REDACTED
            if key in {"user_agent", "precise_location", "latitude", "longitude"}: return "identity", d.REDACTED
            return None

        def collect(obj, depth=0):
            if depth > policy.max_depth: return
            items = ((k, getattr(obj, k)) for k in type(obj).model_fields) if isinstance(obj, BaseModel) else obj.items() if isinstance(obj, dict) else ()
            for key, child in items:
                match = category(key)
                if match and match[0] != "public_client_ip" and isinstance(child, str) and len(child) >= 3 and not child.startswith("[REDACTED"):
                    known[child] = match
                else: collect(child, depth + 1)
            if isinstance(obj, (list, tuple, set)):
                for child in obj: collect(child, depth + 1)

        collect(value)
        if known_context is not None:
            collect(known_context)
        known_values = sorted(known.items(), key=lambda pair: (-len(pair[0]), pair[0]))

        def replace(original, replacement, name):
            if original != replacement: counts[name] += 1
            return replacement

        def text(value, *, limit=True, max_length=None, replace_known=True):
            cutoff = min(policy.max_free_text_length, max_length or policy.max_free_text_length)
            # Remove entire key blocks before any other text operation/truncation.
            value = d.PRIVATE_KEY.sub(lambda m: replace(m[0], d.REDACTED, "credential"), value)
            value = d.URL.sub(lambda m: replace(m[0], sanitize_url(m[0]), "url"), value)
            value = d.HEADER.sub(lambda m: replace(m[0], d.REDACTED, "credential"), value)
            for original, (name, placeholder) in (known_values if replace_known else ()):
                if original in value:
                    counts[name] += value.count(original)
                    value = value.replace(original, placeholder)
            value = d.ASSIGNMENT.sub(lambda m: m[1] + replace(m[2], d.REDACTED, "credential"), value)
            for pattern in (d.AUTH, d.OPAQUE):
                value = pattern.sub(lambda m: replace(m[0], d.REDACTED, "credential"), value)
            def identifier(m):
                match = category(m[1].strip(' \t:=：\"\''))
                return m[1] + replace(m[2], match[1], match[0]) if match else m[0]
            value = d.IDENTIFIER.sub(identifier, value)
            if policy.redact_mac or policy.redact_bssid:
                value = d.MAC_PATTERN.sub(lambda m: replace(m[0], d.MAC, "mac"), value)
            if policy.redact_hostname:
                value = d.HOST_PATTERN.sub(lambda m: replace(m[0], d.HOSTNAME, "hostname"), value)
            for pattern in (d.USER_AGENT, d.LOCATION):
                value = pattern.sub(lambda m: replace(m[0], d.REDACTED, "identity"), value)
            if policy.redact_email:
                value = d.EMAIL.sub(lambda m: replace(m[0], d.REDACTED, "email"), value)
            if policy.redact_phone:
                value = d.PHONE.sub(lambda m: replace(m[0], d.REDACTED, "phone"), value)
            if policy.mask_private_ip:
                pieces, offset = [], 0
                for match in d.URL.finditer(value):
                    pieces.append(IP_PATTERN.sub(lambda m: replace(m[0], mask_address(m[0]), "private_ip"), value[offset:match.start()]))
                    pieces.append(replace(match[0], mask_url_address(match[0]), "private_ip"))
                    offset = match.end()
                pieces.append(IP_PATTERN.sub(lambda m: replace(m[0], mask_address(m[0]), "private_ip"), value[offset:]))
                value = "".join(pieces)
            if truncate and limit and len(value) > cutoff:
                counts["length_limit"] += 1
                warnings.add("text_truncated")
                shortened = value[:cutoff]
                for match in d.URL.finditer(value):
                    if match.start() < cutoff < match.end():
                        shortened = value[:match.start()]
                        if len(shortened) + len(d.REDACTED) <= cutoff:
                            shortened += d.REDACTED
                        break
                opening = shortened.rfind("[REDACTED")
                if opening >= 0 and "]" not in shortened[opening:]:
                    shortened = shortened[:opening]
                # Also avoid cutting the opening part of a placeholder.
                opening = shortened.rfind("[")
                if opening >= 0 and value[opening:].startswith("[REDACTED") and "]" not in shortened[opening:]:
                    shortened = shortened[:opening]
                value = shortened
            return value

        def walk(obj, depth=0, key="", max_length=None):
            if depth > policy.max_depth:
                warnings.add("depth_limit")
                return replace(obj, d.REDACTED, "depth_limit")
            match = category(key)
            if match and obj is not None:
                # Keep collection types stable when a sensitive field is a list.
                if isinstance(obj, (list, tuple)):
                    return type(obj)(replace(item, match[1], match[0]) for item in obj)
                return replace(obj, match[1], match[0])
            if isinstance(obj, BaseModel):
                updates = {k: walk(getattr(obj, k), depth + 1, k,
                                  next((getattr(m, "max_length") for m in field.metadata if getattr(m, "max_length", None) is not None), None))
                           for k, field in type(obj).model_fields.items()
                           if k not in {"privacy_metadata", "privacy_policy_version"}}
                result = obj.model_copy(update=updates)
                # Any newly sanitized package remains a valid immutable artifact.
                if hasattr(result, "package_digest") and updates != {k: getattr(obj, k) for k in updates}:
                    payload = result.model_dump(mode="json", exclude={"package_digest"})
                    result = result.model_copy(update={"package_digest": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()})
                return result
            if isinstance(obj, dict):
                return {text(str(k), limit=False, replace_known=False): walk(v, depth + 1, str(k)) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return type(obj)(walk(item, depth + 1, key) for item in obj)
            if isinstance(obj, set):
                return {walk(item, depth + 1) for item in obj}
            if isinstance(obj, Enum):
                return obj
            if isinstance(obj, str):
                if d.normalize_key(key) in {"url", "source_url", "citation_url", "href"} and obj:
                    obj = replace(obj, sanitize_url(obj), "url")
                return text(obj, max_length=max_length)
            return obj

        sanitized = walk(value)
        return RedactionResult(value=sanitized, changed=bool(counts),
            redacted_categories=sorted(counts), redacted_count=sum(counts.values()), warnings=sorted(warnings))


def redact_mapping(value, policy=None):
    return Redactor(policy).redact(value)


def redact_model(value, policy=None):
    return Redactor(policy).redact(value)


def redact_sequence(value, policy=None):
    return Redactor(policy).redact(value)


def redact_text(value, policy=None, *, truncate=True):
    return Redactor(policy).redact(value, truncate=truncate)


def safe_value(value, policy=None, *, context="presentation"):
    """Typed copy for persistence/presentation, with cumulative value-free metadata."""
    redactor = Redactor(policy)
    result = redactor.redact(value)
    sanitized = result.value
    if isinstance(sanitized, BaseModel) and "privacy_metadata" in type(sanitized).model_fields:
        metadata = metadata_for(result, redactor.policy)
        previous = getattr(value, "privacy_metadata", None)
        if previous:
            metadata.categories = sorted(set(metadata.categories) | set(previous.categories))
            metadata.redacted_count += previous.redacted_count
            metadata.private_ip_masked |= previous.private_ip_masked
            metadata.hostname_redacted |= previous.hostname_redacted
            metadata.sensitive_values_removed |= previous.sensitive_values_removed
        sanitized = sanitized.model_copy(update={"privacy_metadata": metadata,
                                                "privacy_policy_version": redactor.policy.policy_version})
    if isinstance(sanitized, BaseModel) and hasattr(sanitized, "package_digest"):
        payload = sanitized.model_dump(mode="json", exclude={"package_digest"})
        sanitized = sanitized.model_copy(update={"package_digest": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()})
    if result.changed:
        from .logging import audit
        audit(result, context)
    return sanitized


def export_safe(value, policy=None):
    return safe_value(value, policy, context="export")


def redact_evidence(value, policy=None):
    return safe_value(value, policy, context="persistence")


def safe_text_factory(context, policy=None):
    redactor = Redactor(policy)
    return lambda value: None if value is None else redactor.redact(value, known_context=context).value


def redact_headers(headers, policy=None):
    return redact_mapping(dict(headers), policy)

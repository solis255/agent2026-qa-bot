from .models import RedactionMetadata


def metadata_for(result, policy):
    categories = result.redacted_categories
    return RedactionMetadata(policy_version=policy.policy_version, categories=categories,
        redacted_count=result.redacted_count, private_ip_masked="private_ip" in categories,
        hostname_redacted="hostname" in categories, sensitive_values_removed="credential" in categories)

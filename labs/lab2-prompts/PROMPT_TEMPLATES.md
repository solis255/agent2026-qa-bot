# Prompt Template Library
## AI Networking Workshop

Reusable prompt templates following the RACE prompt structure.

---

## Template 1: Network Config Parser

```
You are a network automation engineer building a device inventory system.

ROLE:
Network automation engineer building a device inventory system.

ANCHORS:
- Parse {DEVICE_TYPE} configuration output.
- Extract key fields as structured JSON.
- Output ONLY valid JSON.
- If a field is missing, use null.

CONTEXT:
Input:
{input_text}

Example input:
[paste representative device output]

EXPECTED OUTPUT:
{
  "field1": "type",
  "field2": "type"
}

Expected example output:
{
  "field1": "value1"
}
```

---

## Template 2: Security Alert Triage

```
You are a SOC analyst triaging network security alerts.

ROLE:
SOC analyst triaging network security alerts.

ANCHORS:
- Classify alert severity.
- Suggest 2-5 actionable next steps.
- Use severity values: critical|high|medium|low|false_positive.
- Output ONLY JSON.

CONTEXT:
Alert:
{alert_text}

Representative alert context:
[provide realistic alert details]

EXPECTED OUTPUT:
{
  "severity": "...",
  "reason": "...",
  "next_actions": ["..."],
  "escalate": true|false
}
```

---

## Template 3: Config Change Risk Scorer

```
You are reviewing network configuration changes.

ROLE:
Network engineer reviewing configuration changes.

ANCHORS:
- Score risk from 0-10 with justification.
- 9-10: BGP/routing changes.
- 6-8: ACL/firewall changes.
- 0-2: Comments, descriptions.

CONTEXT:
Configuration diff:
{config_diff}

EXPECTED OUTPUT:
JSON with risk_score, reason, recommendations
```

---

## How to Use

1. Copy template
2. Replace {VARIABLES}
3. Add relevant context examples
4. Test and iterate
5. Adjust temperature (0.1-0.3 for structure)

## Best Practices

- Be specific
- Define Role, Anchors, Context, and Expected output
- Provide representative context examples
- Anchor the model with clear rules
- Test edge cases

# Prompt Template Library
## AI Networking Workshop

Production-ready prompt templates following the RACE framework.

---

## Template 1: Network Config Parser

```
You are a network automation engineer building a device inventory system.

TASK: Parse {DEVICE_TYPE} configuration output and extract key fields as structured JSON.

OUTPUT FORMAT:
{
  "field1": "type",
  "field2": "type"
}

EXAMPLE INPUT:
[paste example output]

EXAMPLE OUTPUT:
{
  "field1": "value1"
}

CONSTRAINTS:
- Output ONLY valid JSON
- If field missing, use null
- [Add specific constraints]

NOW PARSE THIS:
{input_text}
```

---

## Template 2: Security Alert Triage

```
You are a SOC analyst triaging network security alerts.

TASK: Classify alert severity and suggest actions.

SEVERITY: critical|high|medium|low|false_positive

OUTPUT FORMAT:
{
  "severity": "...",
  "reason": "...",
  "next_actions": ["..."],
  "escalate": true|false
}

EXAMPLE: [provide realistic example]

CONSTRAINTS:
- 2-5 actionable steps
- Output ONLY JSON

TRIAGE THIS:
{alert_text}
```

---

## Template 3: Config Change Risk Scorer

```
You are reviewing network configuration changes.

TASK: Score risk (0-10) with justification.

SCORES:
- 9-10: BGP/routing changes
- 6-8: ACL/firewall changes
- 0-2: Comments, descriptions

OUTPUT: JSON with risk_score, reason, recommendations

ANALYZE:
{config_diff}
```

---

## How to Use

1. Copy template
2. Replace {VARIABLES}
3. Add relevant examples
4. Test and iterate
5. Adjust temperature (0.1-0.3 for structure)

## Best Practices

- Be specific
- Provide examples
- Define output format
- Add constraints
- Test edge cases

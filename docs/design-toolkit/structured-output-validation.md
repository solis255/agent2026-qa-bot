# Structured-output validation checklist

Structured output is useful only when the application validates it.

| Validation check | What to confirm | Evidence or notes |
|---|---|---|
| JSON parse | The response can be parsed without manual cleanup |  |
| Required keys | Every required field exists |  |
| Allowed values | Fields use expected values |  |
| Data types | Numbers, strings, arrays, and nulls match the schema |  |
| Source grounding | Values appear in the raw input or tool result |  |
| Uncertainty handling | Missing or ambiguous data is explicit |  |
| Failure path | Invalid output returns a controlled error |  |

## Minimal schema checklist

```yaml
schema_review:
  object_name: "bgp_summary"
  required_fields:
    - device
    - total_peers
    - established_peers
    - neighbors
  allowed_states:
    - Established
    - Idle
    - Active
    - Connect
    - unknown
  validation_rules:
    - "established_peers must be less than or equal to total_peers"
    - "each neighbor must include ip, state, and prefixes"
    - "final answer must mention any neighbor not in Established state"
```

# RACE prompt worksheet

Use this worksheet before adding a prompt to code.

| RACE element | What to write | Draft |
|---|---|---|
| Role | The operational perspective the model should use |  |
| Anchors | Small input and output examples that show the target pattern |  |
| Context | The relevant device, vendor, command, limits, and constraints |  |
| Expected output | Exact format, fields, missing-value rules, and no-extra-text rules |  |

## Reusable skeleton

```text
ROLE:
You are a network automation assistant helping with read-only NetOps tasks.

ANCHORS:
Example input:
<short realistic input>

Example output:
<exact JSON or response shape>

CONTEXT:
Use only the supplied data.
Do not infer live state that is not present in the input.
The workflow is read-only.

EXPECTED OUTPUT:
Return the requested format only.
Do not use markdown fences.
Use null for missing values.
Do not invent device names, counters, neighbors, or causes.

TASK:
<the specific user request or data to process>
```

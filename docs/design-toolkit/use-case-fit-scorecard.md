# Use-case fit scorecard

Use this scorecard before building an agent. If the workflow is deterministic, already automated, or unsafe without human review, a conventional script or runbook may be better.

| Question | Good agent signal | Stop or redesign signal | Notes |
|---|---|---|---|
| Does the task require context from more than one source? | The agent needs alerts, device state, logs, topology, or tickets together | One command or one API call already answers the question |  |
| Does the next step depend on evidence? | The workflow changes based on BGP, interface, log, or reachability results | The workflow is always the same sequence of steps |  |
| Can the first version stay read-only? | The agent can add value by observing, summarizing, and recommending | The first useful version must change configuration |  |
| Can outputs be validated? | Tool results have schemas, allowed values, or deterministic checks | The answer depends only on free-form model judgment |  |
| Can engineers review the evidence? | The system can show tool calls, inputs, outputs, and final reasoning | The answer is a black box with no audit trail |  |
| Is there a clear owner? | A named team owns tool policy, code, logs, and support | Nobody owns it after the demo |  |

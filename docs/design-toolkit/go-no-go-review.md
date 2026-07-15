# Go/no-go review

Before moving beyond read-only use, run one final review.

| Review question | Evidence to check | Decision |
|---|---|---|
| What is the worst thing this agent can do with its current permissions? | Permission model and tool allowlist |  |
| Can we detect that behavior quickly? | Logs, metrics, and alerts |  |
| Can we stop the workflow safely? | Runbook and kill switch test |  |
| Can we explain the agent output using logged tool evidence? | Evidence record and audit log |  |
| Can an engineer override, reject, or challenge the recommendation? | Approval and review workflow |  |
| Are secrets protected from prompts, logs, and repositories? | Secrets review |  |
| Does every risky action require approval? | Tool policy and approval logs |  |
| Would we be comfortable showing the audit trail after an incident? | Sample audit record |  |

## Decision

- [ ] Go
- [ ] No-go
- [ ] Stay read-only and close gaps

Decision notes:

```
Add review notes here.
```

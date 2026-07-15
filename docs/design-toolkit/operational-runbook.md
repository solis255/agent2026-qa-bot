# Operational runbook

Keep the first runbook short and operational.

| Runbook section | What to include | Local details |
|---|---|---|
| Purpose | What the agent is intended to support |  |
| Scope | Approved environments, users, devices, and exclusions |  |
| Startup | Commands, services, or deployment steps |  |
| Health checks | Known safe calls that confirm the workflow is working |  |
| Logs | Where audit and application logs are stored |  |
| Common failures | Known symptoms and first checks |  |
| Escalation | Who owns support and when to contact them |  |
| Disable path | How to stop the workflow or reduce scope |  |

## Disable procedure

1. Stop the application or service.
2. Revoke or rotate any test credentials if needed.
3. Confirm no tool calls are still running.
4. Record the disable action in the pilot log or ticket.

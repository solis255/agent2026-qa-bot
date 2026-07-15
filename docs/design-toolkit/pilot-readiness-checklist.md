# Pilot readiness checklist

Use this before a read-only pilot.

| Readiness area | Minimum expectation | Evidence to attach | Status |
|---|---|---|---|
| Scope | Use case, users, devices, and excluded actions are documented | Scope statement or ticket |  |
| Authentication | Callers are identified before tool access | Identity provider or service account details |  |
| Authorization | Tool access is limited by role or allowlist | RBAC mapping |  |
| Secrets | Credentials are not in prompts, code, or logs | Secrets storage plan |  |
| Validation | Inputs and outputs are checked before use | Schema or validation code |  |
| Logging | Every tool call creates an audit event | Sample log event |  |
| Observability | Tool errors, latency, and blocked requests are visible | Dashboard or metric list |  |
| Failure behavior | Timeouts and invalid outputs fail closed | Failure test results |  |
| Approval gates | Write actions are disabled or require review | Approval policy |  |
| Disable path | The workflow can be stopped quickly | Runbook step or kill switch |  |
| Ownership | Code, tool policy, and operations support have named owners | Owner list |  |

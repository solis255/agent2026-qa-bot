# Feature flag and kill switch template

Use feature flags to limit rollout and kill switches to stop unsafe behavior quickly.

| Control | Purpose | Owner | Default state | Notes |
|---|---|---|---|---|
| Read-only mode | Prevent write actions |  | enabled |  |
| Approved device scope | Limit which devices can be queried |  | lab only |  |
| Tool allowlist | Limit which tools the agent can call |  | enabled |  |
| Approval required | Require human approval for risky actions |  | enabled |  |
| Global disable | Stop all agent tool calls quickly |  | available |  |

## Kill switch test

- [ ] The team knows who can trigger the disable path.
- [ ] The disable path has been tested.
- [ ] The audit log shows when the workflow was disabled.
- [ ] Users receive a clear message when the workflow is disabled.

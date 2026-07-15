# AI network agent design toolkit

This folder contains ready-to-copy versions of the Appendix A worksheets and templates from *Building AI Agents for Network Operations*.

Use these files when you want to move from a lab agent to a reviewed operational prototype. Start with the use-case brief, tool inventory, evidence record, production checklist, runbook, and go/no-go review.

## Files

| File | Purpose |
|---|---|
| `agent-use-case-brief.yaml` | Define the first agent use case, users, scope, exclusions, and success measures |
| `use-case-fit-scorecard.md` | Decide whether the workflow should use an agent, automation, or a manual runbook |
| `race-prompt-worksheet.md` | Design and review RACE prompts before adding them to code |
| `structured-output-validation.md` | Review JSON parsing, required keys, allowed values, types, and failure behavior |
| `memory-context-policy.md` | Define what history, tool results, and context are stored or cleared |
| `tool-inventory-safety-matrix.md` | List approved tools, purposes, inputs, outputs, and safety rules |
| `tool-contract.yaml` | Define a reusable tool contract before exposing a tool through MCP or another client |
| `troubleshooting-evidence-record.yaml` | Record what the agent checked and what evidence supports the final answer |
| `pilot-readiness-checklist.md` | Review scope, access, logging, observability, failures, and ownership before a pilot |
| `operational-runbook.md` | Document how to start, test, monitor, escalate, and disable the agent workflow |
| `feature-flag-kill-switch.md` | Define how to limit, disable, or roll back the workflow safely |
| `go-no-go-review.md` | Capture final review questions before moving beyond read-only use |

Keep these templates version controlled. A small change to a prompt, tool contract, or approval rule can change operational behavior.

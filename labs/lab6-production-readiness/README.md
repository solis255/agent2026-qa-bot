# Lab 6: Production Readiness for Network Agents

This lab answers the question every network engineer eventually asks:

> This worked in the lab. Now how do I keep it from doing something dangerous in production?

The goal is not to create a fully productionized platform in one lab. The goal is to teach the patterns that make AI-assisted NetOps safer, observable, and easier to evaluate before real infrastructure is touched.

## What you will build

You will build a production-readiness skeleton around the workshop network tools:

- A backend abstraction for mock vs. real network access
- A read-only-first tool policy
- Input validation for devices and commands
- Structured logging for tool calls
- Basic retry and timeout patterns
- Approval gates for risky operations
- A safety checklist for moving from lab to controlled evaluation

## Why this matters

Network automation has always had a blast-radius problem. AI agents make that more important, not less.

A good production agent should not be measured only by whether it can answer a question. It should also answer:

- What tools did it call?
- What data did it use?
- Was the command read-only?
- Was the device approved?
- Did a human approve risky action?
- Can we replay what happened later?
- Did the agent fail safely?

If you cannot answer those questions, the agent is not ready for production. It may be a useful demo, but it is not an operational system yet.

## Folder contents

```text
labs/lab6-production-readiness/
├── README.md                       # This guide
├── safe_tools.py                   # Safety wrappers and audit logging
├── production_agent_skeleton.py    # Mock-to-real backend pattern
└── production_checklist.md         # Review checklist before real use
```

## Run the safety wrapper demo

From the repository root:

```bash
python3 labs/lab6-production-readiness/safe_tools.py
```

You should see allowed read-only commands, blocked unsafe commands, and structured audit events.

## Run the production skeleton demo

```bash
python3 labs/lab6-production-readiness/production_agent_skeleton.py
```

This shows how to switch between a mock backend and a future real-device backend without changing the agent-facing tool contract.

## The production pattern

```text
Agent request
  ↓
Tool schema
  ↓
Validation and policy checks
  ↓
Approval gate if needed
  ↓
Backend adapter: mock, SSH, API, controller, NetBox, etc.
  ↓
Structured result
  ↓
Audit log
  ↓
Agent summary
```

The agent should never be the first line of defense. Policy, validation, and approvals belong in code.

## Read-only first

This lab keeps everything read-only by default. That is intentional.

A production path usually looks like this:

1. Observe only
2. Recommend actions
3. Create change requests
4. Require human approval
5. Execute limited changes
6. Expand scope only after evidence and testing

Do not jump from "agent can troubleshoot" to "agent can configure the network" without guardrails.

## Suggested exercises

1. Add a device allowlist for only spine devices.
2. Add a command allowlist for approved `show` commands.
3. Add JSONL audit logging to a file.
4. Create an approval function that requires a ticket ID for risky actions.
5. Replace the mock backend with a Netmiko or Paramiko backend in a lab-only environment.
6. Add latency and error counters for each tool call.

## Book alignment

This lab supports Chapter 9 of the book outline: **Moving toward production-ready network agents**.

By the end of this lab, readers should understand the difference between a working demo and a controlled, observable, read-only-first operational prototype.

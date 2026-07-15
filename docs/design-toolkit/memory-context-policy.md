# Memory and context policy

Define what the application stores and what it sends back to the model.

| Memory decision | Recommended starting point | Local decision |
|---|---|---|
| Session history | Keep recent user and assistant turns for the active investigation |  |
| Older context | Summarize older turns when the session gets long |  |
| Tool results | Store raw results separately from the model response |  |
| Sensitive data | Avoid storing secrets, credentials, or unnecessary payloads |  |
| Reset behavior | Provide a clear reset or new-case command |  |
| Retention | Define how long history and evidence are kept |  |

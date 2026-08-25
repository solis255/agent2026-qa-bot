# Lab 3C: Stateful Chatbot with Device Context

`chatbot_v3_live_ssh.py` extends the stateful chatbot by collecting interface and BGP state, then placing the snapshot in its system message.

The default `USE_MOCK=True` mode needs no network devices. To use real equipment, set `USE_MOCK=False`, update `DEVICE_CONFIG`, and keep commands read-only.

## Run

```powershell
python labs\lab3-chatbot\chatbot_v3_live_ssh.py
```

Interactive commands:

- `refresh`: recollect device data and rebuild the system message.
- `reset`: clear conversation history.
- `quit`: exit.

Code map:

- `LiveDeviceContext.refresh()`: builds a topology snapshot.
- `LiveDeviceContext._fetch()`: chooses mock data or Netmiko SSH.
- `LiveNetworkChatbot._build_system_prompt()`: injects current state.
- `LiveNetworkChatbot.chat()`: sends system message plus history through the TJU API.

Credentials for the model remain in the root `.env`. Device credentials belong in `DEVICE_CONFIG` or a future secret manager and must not be committed.

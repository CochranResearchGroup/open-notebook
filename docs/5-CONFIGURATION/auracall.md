# AuraCall

Open Notebook can use AuraCall as a language-model provider through AuraCall's
OpenAI-compatible local API.

The intended local setup is:

1. Create project-bound AuraCall agents with `POST /v1/agent-setup-handoffs`.
2. Keep the generated client handoff env files under `~/.auracall/clients/`.
3. Register those handoffs in Open Notebook:

```bash
uv run python scripts/register_auracall_models.py
```

The default Open Notebook agent set is:

| Open Notebook choice | AuraCall model |
| --- | --- |
| AuraCall Instant | `agent:open-notebook-instant-chatgpt-soylei` |
| AuraCall Medium | `agent:open-notebook-medium-chatgpt-soylei` |
| AuraCall Pro | `agent:open-notebook-pro-chatgpt-soylei` |

Each model should use a scoped AuraCall API key and the local base URL
`http://127.0.0.1:18095/v1` or the container-reachable equivalent for the live
deployment.

# Model Context Protocol (MCP) Integration

Open Notebook can be integrated into local AI workflows using the **Model Context Protocol (MCP)** in both directions:

- Open Notebook can expose a local MCP server so Codex, OpenClaw, Claude Desktop, VS Code extensions, and other local agents can read and safely update selected Open Notebook resources.
- Open Notebook can also configure local MCP servers under **Advanced -> MCP servers** and inspect their advertised tools for later use in model workflows.

## What is MCP?

The [Model Context Protocol](https://modelcontextprotocol.io) is an open standard that allows AI applications to securely connect to external data sources and tools. With the Open Notebook MCP server, you can:

- 📚 **Access your notebooks** directly from Claude Desktop or VS Code
- 🔍 **Search your research content** without leaving your AI assistant
- 💬 **Create and manage chat sessions** with your research as context
- 📝 **Generate notes** and insights on-the-fly
- 🤖 **Automate workflows** using the full Open Notebook API

## Quick Setup

Open Notebook ships a first-party local MCP entrypoint:

```bash
open-notebook-mcp
```

It talks to the existing Open Notebook HTTP API. Configure it with:

- `OPEN_NOTEBOOK_URL`: API URL, default `http://127.0.0.1:5055`
- `OPEN_NOTEBOOK_PASSWORD`: bearer password when password protection is enabled
- `API_CLIENT_TIMEOUT`: optional HTTP timeout in seconds

The first-party entrypoint intentionally starts with conservative tools:

- read-only: list/get notebooks, list notes, list sources, search, list models, get default models
- write-safe: create notebooks, create notes
- high-risk deletes, embedding rebuilds, and long-running transformations are not exposed by default

## Open Notebook as an MCP Client

Use **Advanced -> MCP servers** to add a local MCP server that Open Notebook can reach. The first implementation supports persisted configuration and stdio tool inspection:

- name, command, arguments, enabled status, timeout, and concurrency
- non-secret environment variables stored as config, with values redacted from API responses
- advertised tool inspection through the MCP `list_tools` call
- per-tool enablement and read/mutate/disabled classification in the stored config
- governed stdio `call_tool` execution through `/api/mcp/tool-call`
- recent tool-call audit inspection through `/api/mcp/tool-audit`

Network transports (`http`, `sse`, and `websocket`) are represented in the config schema for compatibility, but this slice only tests and lists tools for stdio servers. Keep private tokens out of this form; use environment references or the existing credential mechanisms instead.

### Calling MCP tools from notebook chat

Notebook chat supports an explicit read-only MCP command:

```text
/mcp <server-id> <tool-name> <json-args>
```

For example:

```text
/mcp mcp_server_config:local-codegraph codegraph_status {}
```

Open Notebook will call the configured tool only when:

- the server is enabled
- the tool is enabled
- the tool is classified as `read`
- the arguments are a JSON object

The tool result is added to the current chat turn as context before the configured chat model responds. Tools classified as `mutate` are rejected from this read-only chat workflow even when they are configured in Advanced settings.

Direct `/api/mcp/tool-call` requests write audit records with the server/tool name, status, permission class, argument keys, and result size summary. The audit record intentionally stores summaries instead of raw arguments or raw result text.

### Codex App Server MCP profile

The Codex App Server provider card can store a Codex MCP profile preference:

- `No tools`: do not generate Codex MCP config.
- `Read-only local`: generate a Codex config preview for enabled stdio MCP servers that are not classified with mutating tools in Open Notebook.
- `Selected servers`: generate a Codex config preview for explicitly selected enabled stdio MCP servers.
- `Custom profile`: record that Codex is configured outside Open Notebook.

The generated TOML shown in the UI is a preview for Codex-native configuration. It uses environment-variable placeholders for MCP server environment keys and does not write to `CODEX_HOME`, `~/.codex/config.toml`, or any private runtime file.

When Open Notebook launches Codex App Server, it also attempts a conservative Codex-native MCP launch path for the saved `Read-only local` or `Selected servers` profile:

- enabled stdio MCP servers without stored environment values are passed to `codex app-server` as process-local `-c mcp_servers...` overrides
- servers with environment values are written to a private temporary Codex home config so secrets are not exposed through process arguments
- the temporary Codex home symlinks local Codex auth files, writes `config.toml` with mode `0600`, and is removed after the app-server process exits

Codex-native MCP config connects Codex directly to the MCP server. That means it does not enforce Open Notebook's per-tool disabled or mutating classifications. Use the generated config only for trusted read-only servers, and use Open Notebook mediated `/api/mcp/tool-call` or notebook `/mcp ...` commands when you need Open Notebook's guards and audit trail.

For unattended Open Notebook Codex turns, the app-server wrapper automatically accepts Codex's own MCP tool-call confirmation elicitation when `_meta.codex_approval_kind` is `mcp_tool_call`. Other MCP elicitations are declined, because Open Notebook should not collect arbitrary user input inside a background model call.

Open Notebook also contains experimental support for Codex app-server dynamic tools. Set `OPEN_NOTEBOOK_CODEX_APP_SERVER_DYNAMIC_TOOLS=true` to advertise selected read-only MCP tools in `thread/start` config. Codex server-originated `item/tool/call` requests are handled by Open Notebook, routed through the same read-only MCP guardrails, and audited with caller `codex_app_server`. This path is disabled by default because the installed Codex CLI currently treats the advertised namespace as an MCP server unless it is registered in Codex config.

### For Claude Desktop

1. **Install the MCP server**:

   ```bash
   # From this repo checkout:
   uv run open-notebook-mcp
   ```

2. **Configure Claude Desktop**:

   **macOS/Linux**: Edit `~/Library/Application Support/Claude/claude_desktop_config.json`

   ```json
   {
     "mcpServers": {
       "open-notebook": {
         "command": "uv",
         "args": ["run", "--project", "/path/to/open-notebook", "open-notebook-mcp"],
         "env": {
           "OPEN_NOTEBOOK_URL": "http://localhost:5055",
           "OPEN_NOTEBOOK_PASSWORD": "${OPEN_NOTEBOOK_PASSWORD}"
         }
       }
     }
   }
   ```

   **Windows**: Edit `%APPDATA%\Claude\claude_desktop_config.json`

   ```json
   {
     "mcpServers": {
       "open-notebook": {
         "command": "uv",
         "args": ["run", "--project", "C:\\path\\to\\open-notebook", "open-notebook-mcp"],
         "env": {
           "OPEN_NOTEBOOK_URL": "http://localhost:5055",
           "OPEN_NOTEBOOK_PASSWORD": "${OPEN_NOTEBOOK_PASSWORD}"
         }
       }
     }
   }
   ```

3. **Restart Claude Desktop** and start using your notebooks in conversations!

### For VS Code (Cline and other MCP-compatible extensions)

Add to your VS Code settings or `.vscode/mcp.json`:

```json
{
  "servers": {
    "open-notebook": {
      "command": "uvx",
      "args": ["--from", "/path/to/open-notebook", "open-notebook-mcp"],
      "env": {
        "OPEN_NOTEBOOK_URL": "http://localhost:5055",
        "OPEN_NOTEBOOK_PASSWORD": "${OPEN_NOTEBOOK_PASSWORD}"
      }
    }
  }
}
```

### For Codex / OpenClaw-style local agents

Use a stdio MCP server entry that launches the repo-owned command:

```json
{
  "mcpServers": {
    "open-notebook": {
      "command": "uv",
      "args": ["run", "--project", "/home/you/workspace/open-notebook", "open-notebook-mcp"],
      "env": {
        "OPEN_NOTEBOOK_URL": "http://127.0.0.1:5055",
        "OPEN_NOTEBOOK_PASSWORD": "${OPEN_NOTEBOOK_PASSWORD}"
      }
    }
  }
}
```

For the local single-container deployment in this workspace, use the API port
published by Docker, for example `http://127.0.0.1:15055`.

## Configuration

- **OPEN_NOTEBOOK_URL**: URL to your Open Notebook API (default: `http://localhost:5055`)
- **OPEN_NOTEBOOK_PASSWORD**: Optional - only needed if you've enabled password protection

### For Remote Servers

If your Open Notebook instance is running on a remote server, update the URL accordingly:

```json
"OPEN_NOTEBOOK_URL": "http://192.168.1.100:5055"
```

Or with a domain:

```json
"OPEN_NOTEBOOK_URL": "https://notebook.yourdomain.com/api"
```

## What You Can Do

Once connected, you can ask Claude or your AI assistant to:

- _"Search my research notebooks for information about [topic]"_
- _"Create a new note summarizing the key points from our conversation"_
- _"List all my notebooks"_
- _"Start a chat session about [specific source or topic]"_
- _"What sources do I have in my [notebook name] notebook?"_
- _"Add this PDF to my research notebook"_
- _"Show me all notes in [notebook name]"_

The repo-owned MCP server provides a conservative subset of Open Notebook capabilities. Use it for local agent workflows that need notebook discovery, search, model discovery, and safe note/notebook creation.

## Available Tools

The repo-owned Open Notebook MCP server currently exposes these capabilities:

### Notebooks

- List notebooks
- Get notebook details
- Create new notebooks

### Sources

- List sources in a notebook

### Notes

- List notes in a notebook
- Create new notes

### Search

- Vector search across content
- Text search across content

### Models

- List configured AI models
- Get default model settings

### Settings

- High-risk settings mutation is not exposed by default.

## MCP Server Repository

Open Notebook previously documented the external Epochal MCP package:

**🔗 GitHub**: [Epochal-dev/open-notebook-mcp](https://github.com/Epochal-dev/open-notebook-mcp)

Contributions, issues, and feature requests are welcome!

## Finding the Server

The Open Notebook MCP server is published to the official MCP Registry:

- **Registry**: Search for "open-notebook" at [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io)
- **PyPI**: [pypi.org/project/open-notebook-mcp](https://pypi.org/project/open-notebook-mcp)
- **GitHub**: [Epochal-dev/open-notebook-mcp](https://github.com/Epochal-dev/open-notebook-mcp)

## Troubleshooting

### Connection Errors

1. Verify the `OPEN_NOTEBOOK_URL` is correct and accessible
2. If using password protection, ensure `OPEN_NOTEBOOK_PASSWORD` is set correctly
3. For remote servers, make sure port 5055 is accessible from your machine
4. Check firewall settings if connecting to a remote server

## Using with Other MCP Clients

The Open Notebook MCP server follows the standard MCP protocol and can be used with any MCP-compatible client. Check your client's documentation for configuration details.

## Learn More

- [Model Context Protocol Documentation](https://modelcontextprotocol.io)

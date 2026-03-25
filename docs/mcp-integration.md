# MCP Integration

MCP (Model Context Protocol) lets AI agents connect to external services such as GitHub, databases, browsers, and search APIs through a unified tool interface.

---

## How it works

When you add an MCP server, llama-agentic:

1. Connects to the server (via stdio subprocess or remote HTTP)
2. Queries it for its tool list
3. Registers all tools as `mcp_<server>__<toolname>` in the agent

The LLM can then call those tools exactly like built-in tools.

### Current transport support

- **Remote HTTP**: supported through JSON-RPC over HTTP, including Streamable HTTP responses and legacy HTTP+SSE fallback
- **stdio subprocesses**: supported for line-delimited JSON-RPC style servers

### Current limitations

- Remote support is tool-focused: llama-agentic does not yet surface MCP prompts or resources as first-class features.
- The stdio client is not yet a full framed-transport implementation, so some MCP servers may still be incompatible even if they work in other clients.
- When a remote MCP server returns non-text content, llama-agentic currently renders image/resource placeholders or extracted text rather than rich UI content.

---

## Managing MCP servers

### Add a server

```bash
# stdio server (launched as a subprocess)
llama-agent mcp add filesystem \
  --command npx \
  --args "-y @modelcontextprotocol/server-filesystem /" \
  --desc "Sandboxed file access"

# Remote MCP server (already running)
llama-agent mcp add myserver --url http://localhost:3000

# Save to per-project config instead of global
llama-agent mcp add myserver --command ... --local
```

### List configured servers

```bash
llama-agent mcp list
```

### Test a connection

```bash
llama-agent mcp connect filesystem
```

Connects to the server and lists all its exposed tools.

### Remove a server

```bash
llama-agent mcp remove filesystem
```

---

## Config files

MCP server configuration is stored in JSON:

| Scope | Path |
|---|---|
| Global | `~/.config/llama-agentic/mcp.json` |
| Per-project | `.llama-agentic/mcp.json` |

Both files are merged at startup (per-project takes priority).

Example `mcp.json`:

```json
{
  "servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/"],
      "description": "Sandboxed file access",
      "enabled": true
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "description": "GitHub issues and PRs",
      "enabled": true
    },
    "remote-demo": {
      "url": "http://localhost:3000",
      "description": "Remote MCP endpoint",
      "enabled": true
    }
  }
}
```

---

## Popular MCP servers

### File system

```bash
llama-agent mcp add filesystem \
  --command npx \
  --args "-y @modelcontextprotocol/server-filesystem /path/to/sandbox"
```

Provides sandboxed file tools restricted to a directory.

### GitHub

```bash
# Set your token first
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...

llama-agent mcp add github \
  --command npx \
  --args "-y @modelcontextprotocol/server-github"
```

Exposes tools for: list repos, create/read/update issues, PRs, files, commits.

### PostgreSQL

```bash
llama-agent mcp add postgres \
  --command npx \
  --args "-y @modelcontextprotocol/server-postgres postgresql://localhost/mydb"
```

Exposes `query` for read-only SQL access.

### Brave Search

```bash
export BRAVE_API_KEY=...

llama-agent mcp add brave-search \
  --command npx \
  --args "-y @modelcontextprotocol/server-brave-search"
```

### Slack

```bash
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_TEAM_ID=T...

llama-agent mcp add slack \
  --command npx \
  --args "-y @modelcontextprotocol/server-slack"
```

### Docker

```bash
llama-agent mcp add docker \
  --command npx \
  --args "-y mcp-server-docker"
```

### Puppeteer (browser automation)

```bash
llama-agent mcp add puppeteer \
  --command npx \
  --args "-y @modelcontextprotocol/server-puppeteer"
```

---

## Using MCP tools

Once configured, MCP tools appear in the agent automatically. They show up in `/tools` as `mcp_<server>__<toolname>`:

```
/tools
  mcp_github__list_issues      List issues for a repository
  mcp_github__create_issue     Create a new issue
  mcp_postgres__query          Execute a read-only SQL query
  ...
```

The agent uses them just like built-in tools:

```
You: List all open GitHub issues in the llama-agentic repo

Agent: ⚙ mcp_github__list_issues  ✓  Found 3 open issues
       Here are the open issues:
       1. #42 — Tool confirmation default should be Yes not No
       2. #38 — Support streaming for run_shell on Windows
       3. #31 — Add JSON output mode for --task
```

---

## Writing your own MCP server

Any process that speaks the MCP protocol over stdio or remote HTTP can be added, subject to the transport limitations above. See the [MCP specification](https://modelcontextprotocol.io/specification) and [SDK libraries](https://modelcontextprotocol.io/sdk) for details.

Minimal Python MCP server skeleton:

```python
# my_mcp_server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("my-server")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="hello",
            description="Say hello to someone",
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "hello":
        return [TextContent(type="text", text=f"Hello, {arguments['name']}!")]

if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(server))
```

Add it:

```bash
llama-agent mcp add my-server \
  --command python \
  --args "my_mcp_server.py"
```

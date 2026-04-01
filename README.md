# LifeOS MCP Server

A custom Python MCP server that connects any MCP-compatible LLM client to your Obsidian vault, turning it into a persistent life advisor with deep personal context.

---

## What is this?

Your Obsidian vault is your second brain — it holds your personal reflections, knowledge notes, project plans, life goals, and more. LifeOS makes it **active**: every conversation automatically rebuilds and loads a lightweight index of your entire vault, enabling your LLM to reference your thoughts, find patterns across notes, track progress on goals, and collaborate on projects.

**Why an MCP server instead of a system prompt or config file?**
System prompt instructions are suggestions the model can ignore. An MCP server exposes the vault as tools the model naturally reaches for. The server's `instructions` field reliably tells the LLM to load the vault index at conversation start.

**Compatible with any MCP client** — Claude Code, Cursor, Windsurf, or any other tool that supports the [Model Context Protocol](https://modelcontextprotocol.io).

---

## Architecture

```
MCP-compatible client (Claude Code, Cursor, etc.)
  └── 9 MCP tools
  └── Server instructions → auto-load vault index at conversation start

LifeOS MCP Server (Python / FastMCP / stdio)
  └── Rebuilds vault index on every startup
  └── Enforces access zones in code, not just instructions

Obsidian Vault
  └── Configured via setup.py → lifeos.json
```

---

## Vault Structure

LifeOS enforces access zones across your vault folders:

| Folder | LLM reads | LLM writes | Rule |
|--------|-----------|------------|------|
| Brain/ | Yes | No | Sacred, human-only |
| Projects/ | Yes | Yes | Auto-adds `ai-collab` tag |
| Model/ | Yes | Yes | AI's own space |
| Appendix/ | Yes (PDFs) | No | Read-only attachments |
| Templates/ | No | No | Ignored entirely |

You define which of your vault folders maps to which zone in `config.py`.

---

## Tools (9 total)

| Tool | Description |
|------|-------------|
| `get_vault_index` | Full index with summaries, metadata, wikilinks, changelog. Called at every conversation start. |
| `read_note` | Full note content by filename. Searches vault automatically. |
| `search_notes` | Filter by text query, tags, folder, or status. |
| `get_wikilinks` | Full vault link graph, or backlinks/outgoing links for a specific note. |
| `read_pdf` | Extract text from PDFs in the Appendix folder. |
| `get_vault_stats` | Note counts, tag frequency, recent changes, open checklists, active projects, unresolved links. |
| `get_tags` | All tags with frequency counts. Helps the LLM reuse existing tags consistently. |
| `create_note` | Create a new note in Projects/ or Model/. |
| `edit_note` | Edit an existing note in Projects/ or Model/. |

---

## Setup

**1. Clone into your Obsidian vault**

Place the server inside your vault as a hidden folder — this keeps code and vault together and syncs via your cloud provider (OneDrive, iCloud, etc.):
```bash
git clone https://github.com/luis-schoy/lifeos /path/to/your/vault/.lifeos
cd /path/to/your/vault/.lifeos
uv venv
uv pip install fastmcp "PyMuPDF>=1.25" "pyyaml>=6.0" "rich>=13.0"
```

**2. Configure your vault**
```bash
uv run python setup.py
```
Opens a native folder picker. Select your Obsidian vault root. Saves path to `lifeos.json` (gitignored).

**3. Configure folder names**

Open `config.py` and map your vault's folder names to the access zones:
```python
FOLDER_MEMORIA   = "1 - Brain"      # human-only
FOLDER_PROJEKTE  = "2 - Projects"   # shared with LLM
FOLDER_CLAUDE    = "3 - Model"      # AI-only
FOLDER_TEMPLATES = "4 - Templates"  # ignored
FOLDER_ANHAENGE  = "5 - Appendix"   # PDFs
```

**4. Register with your MCP client**

Example for Claude Code:
```bash
claude mcp add --scope user --transport stdio lifeos -- \
  /path/to/uv --project /path/to/your/vault/.lifeos \
  run python /path/to/your/vault/.lifeos/server.py
```

Use `which uv` to get the full path to uv.

**5. Verify**
```bash
claude mcp list
# lifeos: ... ✓ Connected
```

---

## How it works

On every conversation start:
1. The MCP client launches `server.py` as a subprocess
2. `server.py` rebuilds `vault_index.json` from your vault
3. The server's `instructions` tell the LLM to call `get_vault_index` immediately
4. The LLM loads the index and has full vault context for the conversation
5. The client terminates the subprocess when the conversation ends

---

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- An MCP-compatible client (e.g. [Claude Code](https://claude.ai/claude-code))
- An [Obsidian](https://obsidian.md) vault

**Note:** LifeOS is designed specifically for Obsidian — it relies on `[[wikilink]]` syntax, YAML frontmatter conventions, and `obsidian://` URI links. It will work with any Markdown system that follows the same conventions, but Obsidian is the intended target.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Developed with [Claude Code](https://claude.ai/claude-code)*

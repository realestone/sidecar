# Sidecar

A companion tool for Claude Code that analyzes your coding sessions and generates development briefings. Works as both an MCP server (use directly in Claude Code) and a CLI tool.

## What It Does

Sidecar reads your Claude Code session transcripts and uses Claude to generate structured briefings that capture:

- **What got built** — files changed, key code, decisions made
- **How pieces connect** — architecture and data flow
- **Patterns used** — recurring patterns with locations and explanations
- **Will bite you** — potential issues and what to watch for
- **Concepts touched** — what concepts were used and whether the developer understood them

It also manages reusable prompt templates with variable substitution.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Claude Code CLI installed
- Anthropic API key (for session analysis)

## Installation

```bash
# Clone the repo
git clone https://github.com/realestone/sidecar.git
cd sidecar

# Install with uv
uv sync

# Or with pip
pip install -e .
```

## Configuration

### 1. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Add this to your shell profile (`~/.zshrc`, `~/.bashrc`, etc.) to persist it.

### 2. Add Sidecar as an MCP server in Claude Code

Create or edit `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sidecar": {
      "command": "/path/to/sidecar/.venv/bin/python3",
      "args": ["-m", "sidecar.server"]
    }
  }
}
```

Replace `/path/to/sidecar` with your actual installation path.

Alternatively, add a `.mcp.json` file in your project directory for project-specific configuration:

```json
{
  "mcpServers": {
    "sidecar": {
      "command": "/path/to/sidecar/.venv/bin/python3",
      "args": ["-m", "sidecar.server"]
    }
  }
}
```

### 3. (Optional) Enable automatic session analysis

Sidecar can automatically analyze sessions when you stop Claude Code:

```bash
uv run sidecar-cli setup
```

This registers hooks that trigger analysis on session stop. Uses Claude Haiku (~$0.001 per analysis).

To remove hooks:
```bash
uv run sidecar-cli setup --remove
```

## CLI Usage

### Analyze a session

```bash
# Analyze the most recent session
uv run sidecar-cli analyze

# Analyze a specific session
uv run sidecar-cli analyze -s <session-id>

# Re-analyze the most recently briefed session
uv run sidecar-cli analyze --latest

# Output as JSON or Markdown
uv run sidecar-cli analyze -o json
uv run sidecar-cli analyze -o markdown
```

### List sessions

```bash
uv run sidecar-cli sessions

# Filter by project
uv run sidecar-cli sessions -p /path/to/project
```

### View briefings

```bash
# List all briefings
uv run sidecar-cli briefing

# View a specific briefing (compact view)
uv run sidecar-cli briefing -s <session-id>

# View with more detail
uv run sidecar-cli briefing -s <session-id> --detail

# View everything (patterns, concepts, etc.)
uv run sidecar-cli briefing -s <session-id> --full

# View the most recent briefing
uv run sidecar-cli briefing --latest
```

### Check status

```bash
uv run sidecar-cli status
```

## MCP Tools

When running as an MCP server in Claude Code, these tools are available:

### Session Tools

| Tool | Description |
|------|-------------|
| `session_analyze` | Analyze a session and generate a briefing |
| `session_list` | List Claude Code sessions |
| `session_briefing` | Get a previously generated briefing |
| `sidecar_status` | Get overall status (sessions, briefings, insights) |

### Prompt Tools

| Tool | Description |
|------|-------------|
| `prompt_save` | Save a new prompt template with `{{variables}}` |
| `prompt_get` | Get a prompt by name |
| `prompt_use` | Fill variables and return expanded prompt |
| `prompt_list` | List all prompts, optionally by category |
| `prompt_recent` | List recently used prompts |
| `prompt_search` | Search prompts by name/content/category |
| `prompt_delete` | Delete a prompt |

### Example: Using in Claude Code

Just type naturally:

```
session_analyze
```

```
session_list
```

```
session_briefing 6afc3dd1
```

## Data Storage

- **Briefings**: `~/.config/sidecar/briefings/`
- **Prompts**: `~/.config/sidecar/prompts.db` (SQLite)
- **Logs**: `~/.config/sidecar/logs/`
- **Insights**: `~/.config/sidecar/briefings/insights.json`

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_cli.py -v
```

## Cost

Session analysis uses Claude Haiku (`claude-haiku-4-5`), which costs approximately:
- ~$0.001 per session analysis
- Input: $0.25 per million tokens
- Output: $1.25 per million tokens

Most sessions cost less than a penny to analyze.

## License

MIT

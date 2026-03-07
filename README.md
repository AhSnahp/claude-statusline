# Claude Code Custom Statusline

A feature-rich status line for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that goes beyond what the official docs cover.

```
Opus 4.6 | high | Explanatory | main
ctx(200k) ▓▓▓▓▓░░░░░░░░░░░░░░░ 74% left
```

## What it shows

**Line 1:** Model name | thinking effort level | output style | git branch | worktree

**Line 2:** Context window size | compaction-aware usage bar | % remaining | 200k overflow warning

## What makes this different

### Compaction-aware context bar

Claude Code auto-compacts your conversation at ~80% context usage. The remaining 20% is effectively unreachable. This statusline scales the bar so that **80% real usage = 100% visual bar**, giving you a truthful view of how much usable context you actually have left.

| Real usage | Bar shows | Label |
|------------|-----------|-------|
| 0% | empty | 100% left |
| 40% | half full | 50% left |
| 64% | 80% full | 20% left |
| 80% | completely full | 0% left |

Color coding follows the same effective scale:
- **Green:** >50% effective remaining
- **Yellow:** 25-50% effective remaining
- **Red:** <25% effective remaining

### Model thinking effort level (the side-channel trick)

The official [statusline docs](https://code.claude.com/docs/en/statusline) list every JSON field available via stdin. The `effortLevel` setting (which controls extended thinking: `low`, `medium`, `high`) is **not among them**.

The workaround: the statusline command has full filesystem access — it's not sandboxed to the JSON on stdin. So we read `effortLevel` directly from `~/.claude/settings.json`:

```python
def get_effort_level():
    settings_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)
    return settings.get("effortLevel", "")
```

This same technique can expose any setting the JSON API omits.

### Context window size indicator

Shows `200k` or `1M` next to the bar so you always know which context regime you're in.

### 200k overflow warning

`exceeds_200k_tokens` is a fixed boolean threshold regardless of actual window size. When it fires, a red `!200k` warning appears on the bar.

## Installation

### Quick setup

1. Copy the script to your Claude config directory:

```bash
# macOS/Linux
cp statusline.py ~/.claude/statusline.py
chmod +x ~/.claude/statusline.py

# Windows (Git Bash)
cp statusline.py ~/.claude/statusline.py
```

2. Add to `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/statusline.py",
    "padding": 2
  }
}
```

3. Start or resume a Claude Code session. The statusline appears after your first interaction.

### Or just ask Claude Code

```
/statusline
```

Then paste the contents of `statusline.py` when it asks what you want.

## Requirements

- Python 3.7+
- No external dependencies (uses only stdlib: `json`, `os`, `subprocess`, `sys`, `io`)
- A terminal that supports ANSI escape codes (virtually all modern terminals)

## Windows notes

Windows defaults to cp1252 encoding which can't render the Unicode block characters (`▓` and `░`). The script handles this automatically by forcing UTF-8 output:

```python
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
```

## Available JSON fields

The full JSON schema Claude Code sends to statusline commands (as of v2.1.71):

| Field | Description | Used |
|-------|-------------|------|
| `model.display_name` | Current model (e.g. "Opus 4.6") | Line 1 |
| `context_window.used_percentage` | Raw % of context consumed | Bar |
| `context_window.context_window_size` | Total tokens (200k or 1M) | `ctx(200k)` |
| `context_window.remaining_percentage` | Raw % remaining | - |
| `context_window.current_usage.*` | Token breakdown from last API call | - |
| `exceeds_200k_tokens` | Fixed 200k threshold warning | `!200k` |
| `output_style.name` | Active output style | Line 1 |
| `cost.total_cost_usd` | Session spend | - |
| `cost.total_duration_ms` | Session wall-clock time | - |
| `cost.total_api_duration_ms` | Time waiting for API | - |
| `cost.total_lines_added` | Lines of code added | - |
| `cost.total_lines_removed` | Lines of code removed | - |
| `workspace.current_dir` | Current working directory | - |
| `workspace.project_dir` | Directory Claude was launched in | - |
| `session_id` | Unique session ID | - |
| `version` | Claude Code version | - |
| `vim.mode` | `NORMAL` or `INSERT` (when enabled) | - |
| `agent.name` | Agent name (when using `--agent`) | - |
| `worktree.*` | Worktree name, path, branch | Line 1 |

**Not in JSON (side-channel required):**

| Setting | Source | Used |
|---------|--------|------|
| `effortLevel` | `~/.claude/settings.json` | Line 1 |

## Customization

### Change the compaction threshold

If auto-compaction behavior changes, edit the `COMPACTION_THRESHOLD` constant:

```python
COMPACTION_THRESHOLD = 80  # change to match actual compaction point
```

### Change the bar width

```python
bar = build_bar(pct_used, width=30)  # wider bar (default: 20)
```

### Add cost tracking

If you're on a usage-based plan, add cost back to line 2:

```python
cost = data.get("cost", {}).get("total_cost_usd", 0) or 0
cost_str = f" {dim}|{reset} ${cost:.4f}" if cost > 0 else ""
line2 = f"ctx({ctx_label}) {bar} {effective_remaining}% left{exceeds_str}{cost_str}"
```

### Add session duration

```python
duration_ms = data.get("cost", {}).get("total_duration_ms", 0) or 0
mins, secs = duration_ms // 60000, (duration_ms % 60000) // 1000
duration_str = f" {dim}|{reset} {mins}m {secs}s"
```

### Expose other settings via side-channel

```python
def get_setting(key, default=""):
    try:
        path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f).get(key, default)
    except Exception:
        return default
```

## Debugging

Temporarily add a JSON dump to inspect all available fields:

```python
debug_path = os.path.join(os.path.expanduser("~"), ".claude", "statusline_debug.json")
with open(debug_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
```

Then check `~/.claude/statusline_debug.json` after the next render cycle.

## License

MIT

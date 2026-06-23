# Claude Code Custom Statusline

A feature-rich status line for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that goes beyond what the official docs cover — live reasoning effort (including `max` and `ultracode`), per-turn `ultrathink`/`megathink` badges, fast mode, a compaction-aware context bar that knows 200k from 1M, and rate-limit windows.

```
Opus 4.8 (1M context) | ultracode | ✦ultrathink | ⚡fast | default | main
ctx(1M) ▓▓▓▓▓░░░░░░░░░░░░░░░ 74% left
session ▓▓▓▓▓▓░░░░░░░░░░░░░░ 30% used ~2h00m | weekly 29% used ~5h50m
```

## What it shows

**Line 1** (all segments optional except the model):
`model | effort | thinking badge | fast mode | output style | git branch | worktree`

- **effort** — `low` / `medium` / `high` / `xhigh` / `max`, colored as a heat gradient (dim → white → yellow → orange → bold red). `ultracode` is shown in vivid magenta.
- **thinking badge** — `✦ultrathink` (bold magenta) or `✦megathink` (magenta) when those keywords appear in your current prompt.
- **fast mode** — `⚡fast` when `/fast` is active.

**Line 2:** `ctx(1M|200k) | compaction-aware usage bar | % left | !200k overflow warning`

**Line 3** (hidden for API-key users): session (5h) usage bar + weekly (7d) percentage, each with a `~<reset>` countdown.

## What makes this different

### Compaction-aware context bar

Claude Code auto-compacts your conversation at ~80% context usage. The remaining 20% is effectively unreachable. This statusline scales the bar so that **80% real usage = 100% visual bar**, giving you a truthful view of how much usable context you actually have left.

| Real usage | Bar shows | Label |
|------------|-----------|-------|
| 0% | empty | 100% left |
| 40% | half full | 50% left |
| 64% | 80% full | 20% left |
| 80% | completely full | 0% left |

Color coding follows the same effective scale: **green** >50% remaining, **yellow** 25–50%, **red** <25%.

### Reasoning effort level

The effort level (`low`/`medium`/`high`/`xhigh`/`max`) is read live from the statusline JSON at `effort.level`. This matters because **`max` is session-only and is never written to `settings.json`** — so reading it from settings (the old approach) could never display a `max` session correctly. For older Claude Code builds that don't send the field, the script falls back to `effortLevel` in `~/.claude/settings.json`.

### `ultracode` detection (the JSON can't see it)

`/effort ultracode` (= "xhigh + dynamic workflow orchestration") reports to the statusline JSON as plain **`xhigh`** — there is no field or event that distinguishes it. The only on-disk trace is the `/effort` command output in your session transcript. So the script cross-checks: **if `effort.level == "xhigh"` and the most recent `Set effort level to …` line in the transcript is `ultracode`, it shows `ultracode`.** This is session-scoped for free (a new session is a new transcript) and tracks reversions (the latest `/effort` wins).

It's best-effort: it only works when ultracode was set via the `/effort` slash command, and it stops once that marker drifts past the transcript scan cap (8 MB) in a very long session.

### `ultrathink` / `megathink` badges

These are **per-turn prompt keywords**, not persistent settings, and they appear nowhere in the JSON. The script reads your session transcript (`transcript_path`) backward to find the most recent prompt — preferring the clean `last-prompt` event — and badges it. The same backward pass also finds the ultracode marker, so it's a single read.

### Context window size + 1M handling

Shows `1M` or `200k` next to the bar, detected from `context_window_size` with a fallback to the `[1m]` suffix in `model.id`, so a 1M session is never mislabeled. The red `!200k` overflow warning only appears on a real 200k window — on a 1M window, going past 200k is normal, so it's suppressed.

### Rate-limit windows

Reads `rate_limits.five_hour` and `rate_limits.seven_day`: a bar for the 5-hour session window plus the weekly percentage, each with a relative reset countdown (`~2h00m`, `~5h50m`). Colored green/yellow/red by usage. Hidden entirely for API-key users (no `rate_limits` in the JSON). Percentages are `round()`ed because the field is now a float (e.g. `28.999999999999996`).

## Installation

1. Copy the script to your Claude config directory:

```bash
cp statusline.py ~/.claude/statusline.py
chmod +x ~/.claude/statusline.py   # macOS/Linux
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

3. Start or resume a Claude Code session — the statusline appears after your first interaction.

## Requirements

- Python 3.7+
- No external dependencies (stdlib only: `json`, `os`, `subprocess`, `sys`, `io`, `re`, `datetime`)
- A terminal that supports ANSI escape codes and 256-color (virtually all modern terminals)

## Windows notes

Windows defaults to cp1252 encoding, which can't render the Unicode block characters (`▓`/`░`) or the badge glyphs (`✦`/`⚡`). The script handles this by forcing UTF-8 output:

```python
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
```

## Available JSON fields (as of Claude Code v2.1.18x)

| Field | Description | Used |
|-------|-------------|------|
| `model.display_name` | Current model, e.g. "Opus 4.8 (1M context)" | Line 1 |
| `model.id` | Raw id incl. `[1m]` suffix for 1M sessions | 1M detection |
| `effort.level` | Live effort: `low`/`medium`/`high`/`xhigh`/`max` | Line 1 |
| `thinking.enabled` | Whether extended thinking is on | - |
| `fast_mode` | `/fast` mode active | Line 1 |
| `context_window.used_percentage` | Raw % of context consumed | Bar |
| `context_window.context_window_size` | Total tokens (200k or 1000000) | `ctx(…)` |
| `exceeds_200k_tokens` | 200k threshold flag (suppressed on 1M) | `!200k` |
| `output_style.name` | Active output style | Line 1 |
| `rate_limits.five_hour` / `.seven_day` | `used_percentage` (float) + `resets_at` (epoch) | Line 3 |
| `cost.total_cost_usd` | Session spend | - |
| `worktree.*` | Worktree name / branch | Line 1 |
| `transcript_path` | Path to the session `.jsonl` | side-channel |

**Not in the JSON (side-channel required):**

| Signal | Source | Used |
|--------|--------|------|
| `effortLevel` (fallback only) | `~/.claude/settings.json` | Line 1 |
| `ultrathink` / `megathink` | transcript `last-prompt` / user prompt | badge |
| `ultracode` mode | transcript `/effort` command output | Line 1 |

## Customization

Change the compaction threshold or bar width:

```python
COMPACTION_THRESHOLD = 80          # match the actual auto-compaction point
bar = build_bar(pct_used, width=30)  # wider bar (default: 20)
```

Add cost tracking to line 2 (useful on usage-based plans):

```python
cost = data.get("cost", {}).get("total_cost_usd", 0) or 0
cost_str = f" {dim}|{reset} ${cost:.4f}" if cost > 0 else ""
line2 = f"ctx({ctx_label}) {bar} {effective_remaining}% left{exceeds_str}{cost_str}"
```

## Debugging

Temporarily dump the JSON to inspect all available fields:

```python
debug_path = os.path.join(os.path.expanduser("~"), ".claude", "statusline_debug.json")
with open(debug_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
```

Then check `~/.claude/statusline_debug.json` after the next render cycle. Note: `statusline.py` is global across all concurrent Claude Code sessions, so a fixed-path debug file gets overwritten by whichever session renders last — verify `session_id` before trusting a capture.

## License

MIT

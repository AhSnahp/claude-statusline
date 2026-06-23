#!/usr/bin/env python3
"""Claude Code status line: model, git branch, worktree, context bar graph, rate limits."""
import io
import json
import os
import subprocess
import sys

# Force UTF-8 output on Windows (cp1252 can't encode block chars)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def get_git_branch():
    """Get current git branch name, or empty string if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""

def get_effort_level(data):
    """Get the live reasoning effort level (low/medium/high/xhigh/max).

    Claude Code v2.1.18x+ sends the *live* effort in the statusline JSON at
    effort.level. This is the source of truth: it reflects session-only levels
    like `max` that are NEVER written to settings.json (selecting max doesn't
    persist). We fall back to the settings.json side-channel only for older CC
    builds that don't send the field.
    """
    eff = data.get("effort")
    if isinstance(eff, dict):
        level = eff.get("level")
        if level:
            return level
    try:
        settings_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        return settings.get("effortLevel", "")
    except Exception:
        return ""


# Effort levels rendered as a heat gradient: calm -> intense.
# `ultracode` is a special mode (xhigh + workflow orchestration), so it gets its
# own vivid magenta rather than a point on the heat gradient.
EFFORT_COLORS = {
    "low":       "\033[2m",            # dim
    "medium":    "\033[37m",          # white
    "high":      "\033[33m",          # yellow
    "xhigh":     "\033[38;5;208m",    # orange (256-color)
    "max":       "\033[1;38;5;196m",  # bold bright red
    "ultracode": "\033[1;38;5;201m",  # bold vivid magenta (special mode)
}

def effort_color(level):
    """ANSI color for an effort level; defaults to yellow for unknown values."""
    return EFFORT_COLORS.get((level or "").lower(), "\033[33m")


def _keyword_in_prompt(prompt):
    """Map a prompt string to a thinking-keyword badge ('ultrathink'/'megathink'/'')."""
    import re
    low = prompt.lower()
    if "ultrathink" in low:
        return "ultrathink"
    if "megathink" in low or re.search(
        r"think (harder|hard|intensely|really hard|a lot|longer)", low
    ):
        return "megathink"
    return ""


def _extract_prompt(obj):
    """Return the human prompt text from a transcript entry, or None if it isn't a
    genuine human text prompt. Prefers the clean `last-prompt` event (exact prompt
    text, no command-wrapper noise); also accepts plain user text messages.
    """
    t = obj.get("type")
    if t == "last-prompt":
        lp = obj.get("lastPrompt")
        return lp if isinstance(lp, str) and lp.strip() else None
    if t == "user":
        content = obj.get("message", {}).get("content", "")
        if isinstance(content, str):
            return content if content.strip() else None
        if isinstance(content, list):
            # Skip tool-result turns; only consider real text prompts.
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                return None
            txt = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
            return txt if txt.strip() else None
    return None


def read_transcript_signals(transcript_path, want_effort=False):
    """Single backward scan of the session transcript, returning a tuple:
      (thinking_kw, effort_override)

    - thinking_kw  : 'ultrathink' / 'megathink' / '' — the per-turn thinking
      keyword from the most recent human prompt. NOT in the statusline JSON, so we
      read it here as a side-channel.
    - effort_override : the most recent `/effort` selection word (e.g. 'ultracode',
      'max') parsed from the command output, or ''. Only searched when want_effort
      is set. This is the ONLY on-disk trace of `ultracode`, which the JSON masks
      as plain `xhigh` (there is no effort/mode event — `type:mode` is vim mode).

    Reads BACKWARD in 64 KB chunks, stopping as soon as everything needed is found
    (the prompt is normally in the first chunk via the frequently-emitted
    `last-prompt` event). Capped at 8 MB so it still finds an `/effort` marker that
    has drifted far from the end in a long session; beyond that it degrades
    gracefully (thinking keyword still works, ultracode may stop showing). Returns
    ('', '') on any error.
    """
    if not transcript_path:
        return "", ""
    try:
        import re
        effort_re = re.compile(r"effort level to (\w+)", re.IGNORECASE)
        CHUNK = 65536
        CAP = 8 * 1024 * 1024
        thinking = None   # None = not yet found
        effort = None
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as f:
            pos = size
            read_total = 0
            partial = b""
            while pos > 0 and read_total < CAP:
                step = min(CHUNK, pos)
                pos -= step
                f.seek(pos)
                buf = f.read(step) + partial
                read_total += step
                lines = buf.split(b"\n")
                if pos > 0:
                    # First element may be a line split across the chunk boundary;
                    # hold it for the next (earlier) chunk.
                    partial = lines[0]
                    lines = lines[1:]
                else:
                    partial = b""
                for line in reversed(lines):
                    s = line.strip()
                    if not s.startswith(b"{"):
                        continue
                    is_lp = b"last-prompt" in s
                    has_role = b'"role"' in s
                    has_effort = want_effort and effort is None and b"effort level to" in s
                    if not (is_lp or has_role or has_effort):
                        continue  # skip attachments / snapshots / huge base64 lines
                    try:
                        obj = json.loads(s)
                    except Exception:
                        continue
                    if thinking is None:
                        p = _extract_prompt(obj)
                        if p is not None:
                            thinking = _keyword_in_prompt(p)
                    if has_effort:
                        text = None
                        if obj.get("type") == "system":
                            text = obj.get("content")
                        elif obj.get("type") == "user":
                            c = obj.get("message", {}).get("content")
                            text = c if isinstance(c, str) else None
                        if text:
                            m = effort_re.search(text)
                            if m:
                                effort = m.group(1).lower()
                    if thinking is not None and (not want_effort or effort is not None):
                        return thinking, (effort or "")
        return (thinking or ""), (effort or "")
    except Exception:
        return "", ""

def build_bar(pct_used, width=20):
    """Build a color-coded bar graph showing context used before auto-compaction.

    Auto-compaction fires at ~80% real usage, so the bar treats 80% as "full".
    This gives a truthful view of how much usable context remains.
    """
    # Scale: 80% real usage = 100% visual bar (compaction threshold)
    COMPACTION_THRESHOLD = 80
    effective_pct = min(pct_used / COMPACTION_THRESHOLD * 100, 100)
    effective_remaining = 100 - effective_pct
    filled = int(effective_pct * width / 100)
    empty = width - filled

    # Color based on effective remaining context (before compaction)
    if effective_remaining > 50:
        color = "\033[32m"  # green
    elif effective_remaining > 25:
        color = "\033[33m"  # yellow
    else:
        color = "\033[31m"  # red

    reset = "\033[0m"
    bar = "▓" * filled + "░" * empty
    return f"{color}{bar}{reset}"

def format_time_until(epoch_ts):
    """Convert a Unix epoch timestamp to a compact relative time string.

    Returns strings like '2h14m', '47m', '3d5h', or '' if past/invalid.
    """
    from datetime import datetime, timezone
    try:
        target = datetime.fromtimestamp(epoch_ts, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        total_seconds = int((target - now).total_seconds())
        if total_seconds <= 0:
            return ""

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        if days > 0:
            return f"{days}d{hours}h"
        elif hours > 0:
            return f"{hours}h{minutes:02d}m"
        else:
            return f"{minutes}m"
    except Exception:
        return ""

def build_rate_bar(pct_used, width=20):
    """Build a color-coded bar graph showing rate limit usage.

    Unlike the context bar, this maps linearly (no compaction threshold).
    Colors are based on used percentage: green < 50%, yellow 50-80%, red > 80%.
    """
    pct_used = max(0, min(pct_used, 100))
    filled = int(pct_used * width / 100)
    empty = width - filled

    if pct_used > 80:
        color = "\033[31m"   # red
    elif pct_used >= 50:
        color = "\033[33m"   # yellow
    else:
        color = "\033[32m"   # green

    reset = "\033[0m"
    bar = "▓" * filled + "░" * empty
    return f"{color}{bar}{reset}"


def format_rate_line(data):
    """Build line 3: session usage bar + weekly usage percentage.

    Returns the full formatted line, or empty string if rate data is absent.
    """
    rate_limits = data.get("rate_limits")
    if not rate_limits or not isinstance(rate_limits, dict):
        return ""

    dim = "\033[2m"
    reset = "\033[0m"
    parts = []

    # Session (5-hour window) — progress bar
    five_hour = rate_limits.get("five_hour")
    if isinstance(five_hour, dict):
        pct = five_hour.get("used_percentage", 0) or 0
        resets_at = five_hour.get("resets_at")
        bar = build_rate_bar(pct)
        # Color the percentage to match the bar
        if pct > 80:
            color = "\033[31m"
        elif pct >= 50:
            color = "\033[33m"
        else:
            color = "\033[32m"
        time_str = format_time_until(resets_at) if resets_at else ""
        time_part = f" {dim}~{time_str}{reset}" if time_str else ""
        # round: the API now returns floats (e.g. 28.999999999999996)
        parts.append(f"{dim}session{reset} {bar} {color}{round(pct)}%{reset} {dim}used{reset}{time_part}")

    # Weekly (7-day window) — numerical percentage only
    seven_day = rate_limits.get("seven_day")
    if isinstance(seven_day, dict):
        pct = seven_day.get("used_percentage", 0) or 0
        resets_at = seven_day.get("resets_at")
        if pct > 80:
            color = "\033[31m"
        elif pct >= 50:
            color = "\033[33m"
        else:
            color = "\033[32m"
        time_str = format_time_until(resets_at) if resets_at else ""
        time_part = f" {dim}~{time_str}{reset}" if time_str else ""
        parts.append(f"{dim}weekly{reset} {color}{round(pct)}%{reset} {dim}used{reset}{time_part}")

    if not parts:
        return ""

    return f" {dim}|{reset} ".join(parts)

def main():
    data = json.load(sys.stdin)

    # Model
    model = data.get("model", {}).get("display_name", "?")

    # Context window – scale to compaction threshold (80%)
    COMPACTION_THRESHOLD = 80
    ctx = data.get("context_window", {})
    pct_used = ctx.get("used_percentage") or 0
    pct_used = int(pct_used)
    effective_pct = min(pct_used / COMPACTION_THRESHOLD * 100, 100)
    effective_remaining = int(100 - effective_pct)

    # Context window size + 1M detection. Trust context_window_size, but fall back
    # to the model id's [1m] suffix / display name so a 1M session is never
    # mislabeled as 200k if the size field is ever missing.
    model_id = data.get("model", {}).get("id", "")
    ctx_size = ctx.get("context_window_size")
    is_1m = (
        (isinstance(ctx_size, int) and ctx_size >= 1000000)
        or "[1m]" in model_id.lower()
        or "1m" in model.lower()
    )
    if not ctx_size:
        ctx_size = 1000000 if is_1m else 200000
    ctx_label = "1M" if is_1m else f"{ctx_size // 1000}k"

    # The "exceeds 200k" warning only matters on a real 200k window. On a 1M
    # window, going past 200k is normal and expected, so suppress the warning.
    exceeds_200k = data.get("exceeds_200k_tokens", False) and not is_1m

    # Output style (from JSON, no side-channel needed)
    output_style = data.get("output_style", {}).get("name", "")

    # Worktree (only present in --worktree sessions)
    wt = data.get("worktree", {}) or {}
    wt_name = wt.get("name", "")

    # Git branch from worktree data, or fall back to checking git directly
    branch = wt.get("branch", "") or get_git_branch()


    # Build line 1: model | branch | worktree
    dim = "\033[2m"
    reset = "\033[0m"
    cyan = "\033[36m"
    magenta = "\033[35m"

    # Effort level — read live from the JSON (effort.level), which includes the
    # session-only `max` level that never reaches settings.json.
    effort = get_effort_level(data)
    red = "\033[31m"

    # One transcript scan yields both the per-turn thinking keyword AND the session
    # effort override. `ultracode` is invisible in the JSON (it reports as plain
    # `xhigh`), so only dig for the override when we're actually in xhigh.
    think_kw, effort_override = read_transcript_signals(
        data.get("transcript_path", ""), want_effort=(effort == "xhigh")
    )
    if effort == "xhigh" and effort_override == "ultracode":
        effort = "ultracode"

    # Fast mode: Opus with faster output, toggled via /fast
    fast_mode = data.get("fast_mode", False)

    parts = [f"{cyan}{model}{reset}"]
    if effort:
        parts.append(f"{effort_color(effort)}{effort}{reset}")
    if think_kw == "ultrathink":
        parts.append(f"\033[1;35m✦ultrathink{reset}")
    elif think_kw == "megathink":
        parts.append(f"\033[35m✦megathink{reset}")
    if fast_mode:
        parts.append(f"\033[1;33m⚡fast{reset}")
    if output_style:
        parts.append(f"{dim}{output_style}{reset}")
    if branch:
        parts.append(f"{magenta}{branch}{reset}")
    if wt_name:
        parts.append(f"{dim}wt:{reset}{wt_name}")

    line1 = f" {dim}|{reset} ".join(parts)

    # Build line 2: context bar graph
    bar = build_bar(pct_used)
    exceeds_str = f" {red}!200k{reset}" if exceeds_200k else ""
    line2 = f"ctx({ctx_label}) {bar} {effective_remaining}% left{exceeds_str}"

    # Build line 3: session + weekly rate limits
    line3 = format_rate_line(data)

    print(line1)
    print(line2)
    if line3:
        print(line3)

if __name__ == "__main__":
    main()

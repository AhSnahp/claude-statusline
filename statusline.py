#!/usr/bin/env python3
"""Claude Code custom status line.

Displays model name, thinking effort level, output style, git branch,
worktree info, and a compaction-aware context usage bar.

Requires: Python 3.7+ (no external dependencies)
"""
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


def get_effort_level():
    """Read effort level from settings.json (side-channel workaround).

    The effortLevel field is NOT included in the statusline JSON API.
    Since the statusline command has full filesystem access, we read it
    directly from settings.json.
    """
    try:
        settings_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        return settings.get("effortLevel", "")
    except Exception:
        return ""


def build_bar(pct_used, width=20):
    """Build a color-coded bar graph showing context used before auto-compaction.

    Auto-compaction fires at ~80% real usage, so the bar treats 80% as "full".
    This gives a truthful view of how much usable context remains.
    """
    COMPACTION_THRESHOLD = 80
    effective_pct = min(pct_used / COMPACTION_THRESHOLD * 100, 100)
    effective_remaining = 100 - effective_pct
    filled = int(effective_pct * width / 100)
    empty = width - filled

    if effective_remaining > 50:
        color = "\033[32m"  # green
    elif effective_remaining > 25:
        color = "\033[33m"  # yellow
    else:
        color = "\033[31m"  # red

    reset = "\033[0m"
    bar = "\u2593" * filled + "\u2591" * empty
    return f"{color}{bar}{reset}"


def main():
    data = json.load(sys.stdin)

    # Model
    model = data.get("model", {}).get("display_name", "?")

    # Context window - scale to compaction threshold (80%)
    COMPACTION_THRESHOLD = 80
    ctx = data.get("context_window", {})
    pct_used = ctx.get("used_percentage") or 0
    pct_used = int(pct_used)
    effective_pct = min(pct_used / COMPACTION_THRESHOLD * 100, 100)
    effective_remaining = int(100 - effective_pct)

    # Context window size (200k vs 1M)
    ctx_size = ctx.get("context_window_size", 200000)
    ctx_label = "1M" if ctx_size >= 1000000 else f"{ctx_size // 1000}k"

    # Exceeds 200k warning (fixed threshold regardless of window size)
    exceeds_200k = data.get("exceeds_200k_tokens", False)

    # Output style (from JSON, no side-channel needed)
    output_style = data.get("output_style", {}).get("name", "")

    # Worktree (only present in --worktree sessions)
    wt = data.get("worktree", {}) or {}
    wt_name = wt.get("name", "")

    # Git branch from worktree data, or fall back to checking git directly
    branch = wt.get("branch", "") or get_git_branch()

    # ANSI codes
    dim = "\033[2m"
    reset = "\033[0m"
    cyan = "\033[36m"
    magenta = "\033[35m"
    yellow = "\033[33m"
    red = "\033[31m"

    # Effort level (side-channel: read from settings.json)
    effort = get_effort_level()

    # Line 1: model | effort | style | branch | worktree
    parts = [f"{cyan}{model}{reset}"]
    if effort:
        parts.append(f"{yellow}{effort}{reset}")
    if output_style:
        parts.append(f"{dim}{output_style}{reset}")
    if branch:
        parts.append(f"{magenta}{branch}{reset}")
    if wt_name:
        parts.append(f"{dim}wt:{reset}{wt_name}")

    line1 = f" {dim}|{reset} ".join(parts)

    # Line 2: context bar graph
    bar = build_bar(pct_used)
    exceeds_str = f" {red}!200k{reset}" if exceeds_200k else ""
    line2 = f"ctx({ctx_label}) {bar} {effective_remaining}% left{exceeds_str}"

    print(line1)
    print(line2)


if __name__ == "__main__":
    main()

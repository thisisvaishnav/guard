"""Claude Code Stop Hook Integration Writer.

Installs, uninstalls, and checks status of Guard's Stop hook in Claude Code settings.
- By default writes to `.claude/settings.local.json` (uncommitted local settings).
- Supports `--shared` for `.claude/settings.json` (team committed settings).
- Merges into existing `hooks.Stop` array, preserving all other configuration.
- Creates `.bak` backups before modifying existing files.
"""
from __future__ import annotations
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

HOOK_COMMAND = "guard hook stop"
SESSION_START_COMMAND = "guard hook session-start"
SESSION_START_MATCHER = "startup|resume|clear|compact|fork"
DEFAULT_HOOK_TIMEOUT = 180


def get_guard_executable() -> str:
    """Returns the absolute path to the guard executable."""
    guard_bin = shutil.which("guard")
    if guard_bin:
        return str(Path(guard_bin).resolve())
    py_dir = Path(sys.executable).parent
    guard_candidate = py_dir / "guard"
    if guard_candidate.is_file() and os.access(guard_candidate, os.X_OK):
        return str(guard_candidate.resolve())
    if sys.argv and Path(sys.argv[0]).name in ("guard", "guard-cli"):
        return str(Path(sys.argv[0]).resolve())
    return "guard"


def get_settings_path(repo_path: str | Path | None = None, shared: bool = False) -> Path:
    """Returns the path to Claude Code settings file."""
    base = Path(repo_path).resolve() if repo_path else Path.cwd()
    if shared:
        return base / ".claude" / "settings.json"
    local_file = base / ".claude" / "settings.local.json"
    shared_file = base / ".claude" / "settings.json"
    if not local_file.exists() and shared_file.exists():
        return shared_file
    return local_file


def _matches_command(cmd: str, target: str) -> bool:
    if not isinstance(cmd, str):
        return False
    if cmd == target:
        return True
    if target in (HOOK_COMMAND, "stop", "hook stop"):
        return "hook stop" in cmd
    if target in (SESSION_START_COMMAND, "session-start", "hook session-start"):
        return "hook session-start" in cmd
    return target in cmd


def _contains_guard_hook(item: Any, command: str = HOOK_COMMAND) -> bool:
    if isinstance(item, dict):
        if _matches_command(item.get("command", ""), command):
            return True
        inner = item.get("hooks", [])
        if isinstance(inner, list):
            return any(
                isinstance(h, dict) and _matches_command(h.get("command", ""), command)
                for h in inner
            )
    return False


def status(repo_path: str | Path | None = None, shared: bool = False) -> dict[str, Any]:
    """Checks whether Guard Stop hook is installed in Claude settings."""
    settings_file = get_settings_path(repo_path, shared=shared)
    if not settings_file.exists():
        return {
            "installed": False,
            "target_file": str(settings_file),
            "exists": False,
            "shared": shared,
        }

    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        hooks = data.get("hooks", {})
        stop_hooks = hooks.get("Stop", [])
        start_hooks = hooks.get("SessionStart", [])
        if not isinstance(stop_hooks, list):
            stop_hooks = []
        if not isinstance(start_hooks, list):
            start_hooks = []

        installed = any(_contains_guard_hook(h) for h in stop_hooks)
        session_start_installed = any(
            _contains_guard_hook(h, SESSION_START_COMMAND) for h in start_hooks
        )
        return {
            "installed": installed,
            "session_start_installed": session_start_installed,
            "target_file": str(settings_file),
            "exists": True,
            "shared": shared,
            "stop_hooks_count": len(stop_hooks),
        }
    except Exception as exc:
        return {
            "installed": False,
            "target_file": str(settings_file),
            "exists": True,
            "shared": shared,
            "error": str(exc),
        }


def check_all_settings(repo_path: str | Path | None = None) -> dict[str, Any]:
    """Checks whether Guard Stop hook is installed in either local or shared settings."""
    local_stat = status(repo_path=repo_path, shared=False)
    shared_stat = status(repo_path=repo_path, shared=True)
    installed = local_stat["installed"] or shared_stat["installed"]
    active_target = local_stat["target_file"] if local_stat["installed"] else (
        shared_stat["target_file"] if shared_stat["installed"] else local_stat["target_file"]
    )
    return {
        "installed": installed,
        "local": local_stat,
        "shared": shared_stat,
        "active_target": active_target,
    }


def install(
    repo_path: str | Path | None = None,
    shared: bool = False,
    guard_executable: str | None = None,
) -> tuple[bool, str]:
    """Installs the Guard Stop hook into Claude Code settings.
    
    Returns:
        (success: bool, message: str)
    """
    settings_file = get_settings_path(repo_path, shared=shared)
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}
    if settings_file.exists():
        # Backup original
        bak_file = settings_file.with_suffix(settings_file.suffix + ".bak")
        shutil.copy2(settings_file, bak_file)
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
        except Exception as exc:
            return False, f"Failed to parse existing {settings_file}: {exc}"

    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        data["hooks"] = hooks

    stop_hooks = hooks.setdefault("Stop", [])
    if not isinstance(stop_hooks, list):
        stop_hooks = []
        hooks["Stop"] = stop_hooks

    start_hooks = hooks.setdefault("SessionStart", [])
    if not isinstance(start_hooks, list):
        start_hooks = []
        hooks["SessionStart"] = start_hooks

    # Configure command alias
    commands = data.setdefault("commands", {})
    if isinstance(commands, dict):
        commands["guard"] = "guard run"

    stop_present = any(_contains_guard_hook(h) for h in stop_hooks)
    start_present = any(_contains_guard_hook(h, SESSION_START_COMMAND) for h in start_hooks)
    if stop_present and start_present:
        return True, f"Guard hooks are already installed in {settings_file}"

    from guard_cli.hook import get_hook_timeout
    timeout = get_hook_timeout(repo_path)

    guard_exe = guard_executable or get_guard_executable()
    stop_cmd = f"{guard_exe} hook stop"
    session_start_cmd = f"{guard_exe} hook session-start"

    # Claude Code expects matcher objects with a 'hooks' list
    # (https://docs.anthropic.com/en/docs/claude-code/hooks).
    # For the Stop event no tool matcher applies, so "matcher" is empty.
    if not stop_present:
        stop_hooks.append({
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": stop_cmd,
                    "timeout": timeout,
                }
            ]
        })

    # SessionStart records the baseline SHA as early as possible so a fresh
    # session ID can never redefine the baseline to a broken HEAD.
    if not start_present:
        start_hooks.append({
            "matcher": SESSION_START_MATCHER,
            "hooks": [
                {
                    "type": "command",
                    "command": session_start_cmd,
                    "timeout": timeout,
                }
            ]
        })

    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True, f"Successfully installed Guard hooks into {settings_file}"


def uninstall(repo_path: str | Path | None = None, shared: bool = False) -> tuple[bool, str]:
    """Uninstalls Guard Stop hook from Claude Code settings.
    
    Returns:
        (success: bool, message: str)
    """
    settings_file = get_settings_path(repo_path, shared=shared)
    if not settings_file.exists():
        return True, f"Settings file {settings_file} does not exist, nothing to uninstall"

    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return True, "No valid settings found"
    except Exception as exc:
        return False, f"Failed to read {settings_file}: {exc}"

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return True, "No hooks config found"

    # Backup before modification
    bak_file = settings_file.with_suffix(settings_file.suffix + ".bak")
    shutil.copy2(settings_file, bak_file)

    modified = False
    for event, command in (("Stop", HOOK_COMMAND), ("SessionStart", SESSION_START_COMMAND)):
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        filtered = [h for h in entries if not _contains_guard_hook(h, command)]
        if len(filtered) != len(entries):
            modified = True
            if filtered:
                hooks[event] = filtered
            else:
                del hooks[event]

    if not modified:
        return True, f"Guard hooks were not found in {settings_file}"

    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True, f"Successfully removed Guard hooks from {settings_file}"

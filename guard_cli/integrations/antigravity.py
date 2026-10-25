"""Antigravity (App / CLI / IDE) Stop Hook Integration Writer.

Installs, uninstalls, and checks status of Guard's Stop hook in .agents/hooks.json.
- Merges into existing `hooks.json` config.
- Preserves all other configured hooks and handlers.

Format verified against official Antigravity docs (antigravity.google/docs/hooks):
the top level maps hook names to event configs; for Stop (like PreInvocation and
PostInvocation) handler objects sit directly under the event key (matcher is
ignored), each supporting {type: "command", command, timeout}. Stop hooks
re-enter the loop by emitting {"decision": "continue", "reason": ...} on stdout
(exit 0); any other decision (or silent exit 0) allows the stop.

EXPERIMENTAL: verified against the published schema and simulated stdin/stdout
only; a live Antigravity session has not yet confirmed end-to-end behavior.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any

import os
import sys

HOOK_COMMAND = "guard hook stop"
SESSION_START_COMMAND = "guard hook session-start"
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


def get_hooks_file_path(repo_path: str | Path | None = None) -> Path:
    """Returns the path to Antigravity .agents/hooks.json."""
    base = Path(repo_path).resolve() if repo_path else Path.cwd()
    return base / ".agents" / "hooks.json"


def _find_guard_hook(handlers: list[dict[str, Any]], subcmd: str) -> dict[str, Any] | None:
    for h in handlers:
        if isinstance(h, dict):
            cmd = h.get("command", "")
            if f"hook {subcmd}" in cmd:
                return h
    return None


def _contains_guard_hook(handlers: list[dict[str, Any]], subcmd_or_cmd: str = "stop") -> bool:
    for h in handlers:
        if isinstance(h, dict):
            cmd = h.get("command", "")
            if f"hook {subcmd_or_cmd}" in cmd or cmd == subcmd_or_cmd:
                return True
    return False


def status(repo_path: str | Path | None = None) -> dict[str, Any]:
    """Checks whether Guard Stop hook is installed in Antigravity .agents/hooks.json."""
    hooks_file = get_hooks_file_path(repo_path)
    if not hooks_file.exists():
        return {
            "installed": False,
            "target_file": str(hooks_file),
            "exists": False,
        }

    try:
        with open(hooks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"installed": False, "target_file": str(hooks_file), "exists": True}

        # Check all named hooks for a Stop event handler running Guard hook stop
        for hook_name, hook_cfg in data.items():
            if isinstance(hook_cfg, dict):
                stop_handlers = hook_cfg.get("Stop", [])
                stop_hook = _find_guard_hook(stop_handlers, "stop") if isinstance(stop_handlers, list) else None
                if stop_hook:
                    pre_handlers = hook_cfg.get("PreInvocation", [])
                    session_handlers = hook_cfg.get("SessionStart", [])
                    cmd = stop_hook.get("command", "")
                    exe_path = cmd.split()[0] if cmd else ""
                    exe_exists = (
                        Path(exe_path).is_file()
                        if (exe_path and exe_path != "guard")
                        else bool(shutil.which("guard"))
                    )
                    return {
                        "installed": True,
                        "target_file": str(hooks_file),
                        "exists": True,
                        "hook_name": hook_name,
                        "command": cmd,
                        "executable_path": exe_path,
                        "executable_exists": exe_exists,
                        "pre_invocation_installed": (
                            isinstance(pre_handlers, list)
                            and _contains_guard_hook(pre_handlers, "session-start")
                        ),
                        "session_start_installed": (
                            isinstance(session_handlers, list)
                            and _contains_guard_hook(session_handlers, "session-start")
                        ),
                    }
        return {"installed": False, "target_file": str(hooks_file), "exists": True}
    except Exception as exc:
        return {
            "installed": False,
            "target_file": str(hooks_file),
            "exists": True,
            "error": str(exc),
        }


def install(repo_path: str | Path | None = None, guard_executable: str | None = None) -> tuple[bool, str]:
    """Installs Guard Stop hook into .agents/hooks.json.
    
    Returns:
        (success: bool, message: str)
    """
    hooks_file = get_hooks_file_path(repo_path)
    hooks_file.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}
    if hooks_file.exists():
        bak_file = hooks_file.with_suffix(hooks_file.suffix + ".bak")
        shutil.copy2(hooks_file, bak_file)
        try:
            with open(hooks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
        except Exception as exc:
            return False, f"Failed to parse existing {hooks_file}: {exc}"

    guard_hook = data.setdefault("guard-stop", {})
    if not isinstance(guard_hook, dict):
        guard_hook = {}
        data["guard-stop"] = guard_hook

    stop_list = guard_hook.setdefault("Stop", [])
    if not isinstance(stop_list, list):
        stop_list = []
        guard_hook["Stop"] = stop_list

    session_start_list = guard_hook.setdefault("SessionStart", [])
    if not isinstance(session_start_list, list):
        session_start_list = []
        guard_hook["SessionStart"] = session_start_list

    # Clean up legacy PreInvocation if present in guard-stop
    if "PreInvocation" in guard_hook and isinstance(guard_hook["PreInvocation"], list):
        guard_hook["PreInvocation"] = [
            h for h in guard_hook["PreInvocation"]
            if not (isinstance(h, dict) and ("hook session-start" in h.get("command", "") or h.get("command") == SESSION_START_COMMAND))
        ]
        if not guard_hook["PreInvocation"]:
            del guard_hook["PreInvocation"]

    stop_present = _contains_guard_hook(stop_list, "stop")
    session_start_present = _contains_guard_hook(session_start_list, "session-start")
    if stop_present and session_start_present:
        return True, f"Guard hooks are already installed in {hooks_file}"

    from guard_cli.hook import get_hook_timeout
    timeout = get_hook_timeout(repo_path)

    guard_exe = guard_executable or get_guard_executable()
    stop_cmd = f"{guard_exe} hook stop"
    session_start_cmd = f"{guard_exe} hook session-start"

    if not stop_present:
        stop_list.append({
            "type": "command",
            "command": stop_cmd,
            "timeout": timeout,
        })

    # SessionStart records the baseline SHA at session start.
    if not session_start_present:
        session_start_list.append({
            "type": "command",
            "command": session_start_cmd,
            "timeout": 30,
        })

    with open(hooks_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True, f"Successfully installed Guard hooks into {hooks_file}"


def uninstall(repo_path: str | Path | None = None) -> tuple[bool, str]:
    """Uninstalls Guard Stop hook from .agents/hooks.json."""
    hooks_file = get_hooks_file_path(repo_path)
    if not hooks_file.exists():
        return True, f"Hooks file {hooks_file} does not exist, nothing to uninstall"

    try:
        with open(hooks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return True, "No valid hooks config found"
    except Exception as exc:
        return False, f"Failed to read {hooks_file}: {exc}"

    modified = False
    for hook_name, hook_cfg in list(data.items()):
        if not isinstance(hook_cfg, dict):
            continue
        container_modified = False
        for event, subcmd in (("Stop", "stop"), ("PreInvocation", "session-start"), ("SessionStart", "session-start")):
            orig = hook_cfg.get(event)
            if not isinstance(orig, list):
                continue
            new_list = [
                h for h in orig
                if not (isinstance(h, dict) and (f"hook {subcmd}" in h.get("command", "") or h.get("command") in (HOOK_COMMAND, SESSION_START_COMMAND)))
            ]
            if len(new_list) != len(orig):
                if new_list:
                    hook_cfg[event] = new_list
                else:
                    del hook_cfg[event]
                container_modified = True
        if container_modified:
            modified = True
            if not hook_cfg:
                del data[hook_name]

    if not modified:
        return True, f"Guard Stop hook was not found in {hooks_file}"

    bak_file = hooks_file.with_suffix(hooks_file.suffix + ".bak")
    shutil.copy2(hooks_file, bak_file)

    with open(hooks_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return True, f"Successfully removed Guard Stop hook from {hooks_file}"

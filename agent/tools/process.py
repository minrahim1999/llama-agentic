"""Process management tools — list running processes, kill by PID, and manage
background processes started within the current agent session."""

import collections
import os
import platform
import re
import signal
import socket
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from agent.tools import tool

# ── Background-process registry ───────────────────────────────────────────────

_TAIL = 50          # lines of stdout kept per background process
_PORT_SEARCH = 20   # how many ports to scan above the default

# pid → {proc, command, cwd, port, started, buf}
_BACKGROUND_PROCS: dict[int, dict] = {}


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _find_free_port(start: int) -> int:
    for p in range(start, start + _PORT_SEARCH):
        if _is_port_free(p):
            return p
    raise RuntimeError(f"No free port found in {start}–{start + _PORT_SEARCH - 1}")


_PORT_RE = [
    re.compile(r"(--port[=\s]+)(\d+)"),   # --port 3000 / --port=3000
    re.compile(r"(-p\s+)(\d+)"),           # -p 3000
    re.compile(r"(PORT=)(\d+)"),           # PORT=3000 env prefix
    re.compile(r"(:)(\d{4,5})\b"),         # :3000 URL-style
]


def _extract_port(command: str) -> int | None:
    for pat in _PORT_RE:
        m = pat.search(command)
        if m:
            return int(m.group(2))
    return None


def _substitute_port(command: str, old: int, new: int) -> str:
    return command.replace(str(old), str(new))


def _drain(proc: subprocess.Popen, buf: "collections.deque[str]") -> None:
    """Daemon thread: read combined stdout/stderr into a rolling deque."""
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            buf.append(line.rstrip())
    except Exception:
        pass


def kill_all_background() -> int:
    """Terminate every background process tracked in this session.

    Called automatically when the REPL exits. Returns the number of
    processes that were still running and had to be killed.
    """
    killed = 0
    for pid, info in list(_BACKGROUND_PROCS.items()):
        proc: subprocess.Popen = info["proc"]
        if proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                killed += 1
            except Exception:
                pass
    _BACKGROUND_PROCS.clear()
    return killed


@tool
def process_list(filter: str = "") -> str:
    """List running processes, optionally filtered by name.

    Args:
        filter: Case-insensitive substring to filter process names. Empty returns all.
    """
    system = platform.system().lower()
    try:
        if system == "windows":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True,
            )
            lines = result.stdout.strip().splitlines()
            # CSV format: "Image Name","PID","Session Name","Session#","Mem Usage"
            parsed = []
            for line in lines:
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 2:
                    name, pid = parts[0], parts[1]
                    if not filter or filter.lower() in name.lower():
                        parsed.append(f"{pid:>8}  {name}")
            return "     PID  Name\n" + "\n".join(parsed) if parsed else "No matching processes."
        else:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True,
            )
            lines = result.stdout.strip().splitlines()
            if filter:
                header = lines[0] if lines else ""
                matched = [line for line in lines[1:] if filter.lower() in line.lower()]
                if not matched:
                    return f"No processes matching '{filter}'."
                return header + "\n" + "\n".join(matched)
            return result.stdout.strip()
    except Exception as e:
        return f"Error listing processes: {e}"


@tool
def kill_process(pid: int, force: bool = False) -> str:
    """Send a termination signal to a process by PID.

    Args:
        pid: Process ID to terminate.
        force: If true, send SIGKILL (force kill) instead of SIGTERM (graceful).
    """
    system = platform.system().lower()
    try:
        if system == "windows":
            cmd = ["taskkill", "/PID", str(pid)]
            if force:
                cmd.append("/F")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return f"Process {pid} terminated."
            return f"Error: {result.stderr.strip() or result.stdout.strip()}"
        else:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
            return f"Sent {'SIGKILL' if force else 'SIGTERM'} to PID {pid}."
    except ProcessLookupError:
        return f"Error: no process with PID {pid}."
    except PermissionError:
        return f"Error: permission denied to kill PID {pid}."
    except Exception as e:
        return f"Error: {e}"


@tool
def run_background(command: str, cwd: str = "", env_vars: str = "", port: int = 0) -> str:
    """Start a long-running command in the background (dev server, watcher, etc.).

    The chat remains usable while the process runs. All background processes
    are automatically killed when the session ends. If the intended port is
    already in use, the next free port near it is chosen automatically.

    Args:
        command: Shell command to start (e.g. 'npm start', 'uvicorn app:app --port 8000').
        cwd: Working directory. Empty means current directory.
        env_vars: Extra KEY=VALUE env vars separated by spaces (e.g. 'NODE_ENV=production').
        port: Port hint for conflict detection. Auto-detected from the command if 0.
    """
    env = os.environ.copy()
    if env_vars:
        for pair in env_vars.split():
            if "=" in pair:
                k, v = pair.split("=", 1)
                env[k] = v

    work_dir: str | None = None
    if cwd:
        work_dir = str(Path(cwd).expanduser().resolve())

    # Duplicate-process guard: reject if same command is still running
    for pid, info in _BACKGROUND_PROCS.items():
        proc: subprocess.Popen = info["proc"]
        if proc.poll() is None and info["command"].strip() == command.strip():
            return (
                f"Already running: PID {pid}  [{info['command']}]  "
                f"started {info['started']}. Use list_background to check its output "
                f"or stop_background {pid} to stop it first."
            )

    # Port conflict resolution
    hint_port: int | None = port or _extract_port(command)
    actual_port: int | None = None
    port_note = ""

    if hint_port:
        if not _is_port_free(hint_port):
            actual_port = _find_free_port(hint_port + 1)
            command = _substitute_port(command, hint_port, actual_port)
            if "PORT" in env and env["PORT"] == str(hint_port):
                env["PORT"] = str(actual_port)
            port_note = f"Port {hint_port} busy → using {actual_port}"
        else:
            actual_port = hint_port
            port_note = f"Port {actual_port}"

    proc = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=work_dir,
        env=env,
        start_new_session=True,
    )

    buf: collections.deque[str] = collections.deque(maxlen=_TAIL)
    threading.Thread(target=_drain, args=(proc, buf), daemon=True).start()

    pid = proc.pid
    _BACKGROUND_PROCS[pid] = {
        "proc": proc,
        "command": command,
        "cwd": work_dir or str(Path.cwd()),
        "port": actual_port,
        "started": datetime.now().strftime("%H:%M:%S"),
        "buf": buf,
    }

    lines = [f"Background process started  PID {pid}"]
    if port_note:
        lines.append(port_note)
    lines.append(f"Command: {command}")
    lines.append("Use list_background to check status / output, stop_background <pid> to stop.")
    return "\n".join(lines)


@tool
def list_background(tail: int = 10) -> str:
    """List background processes started in this session with recent output.

    Args:
        tail: Number of recent output lines to show per process (default 10).
    """
    if not _BACKGROUND_PROCS:
        return "No background processes running in this session."

    parts: list[str] = []
    for pid, info in _BACKGROUND_PROCS.items():
        proc: subprocess.Popen = info["proc"]
        status = "running" if proc.poll() is None else f"exited ({proc.returncode})"
        port_str = f"  port {info['port']}" if info["port"] else ""
        header = f"PID {pid}  [{status}]{port_str}  started {info['started']}"
        header += f"\n  cmd: {info['command']}"
        recent = list(info["buf"])[-tail:]
        if recent:
            output = "\n".join(f"  │ {line}" for line in recent)
            parts.append(f"{header}\n{output}")
        else:
            parts.append(f"{header}\n  │ (no output yet)")

    return "\n\n".join(parts)


@tool
def stop_background(pid: int) -> str:
    """Stop a background process started in this session by PID.

    Args:
        pid: PID returned by run_background.
    """
    if pid not in _BACKGROUND_PROCS:
        return f"PID {pid} not found in background process registry."

    info = _BACKGROUND_PROCS.pop(pid)
    proc: subprocess.Popen = info["proc"]
    if proc.poll() is not None:
        return f"PID {pid} had already exited (code {proc.returncode})."

    proc.terminate()
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.kill()
    return f"PID {pid} stopped.  ({info['command']})"

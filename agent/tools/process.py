"""Process management tools — list running processes and kill by PID."""

import os
import platform
import signal
import subprocess
from agent.tools import tool


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

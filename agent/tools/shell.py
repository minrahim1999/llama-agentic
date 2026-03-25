"""Shell execution tool."""

import os
import subprocess
import sys
from pathlib import Path
from agent.tools import tool


@tool
def run_shell(command: str, cwd: str = "", timeout: int = 30, env_vars: str = "") -> str:
    """Run a shell command and return its output.

    Args:
        command: Shell command to execute (passed to the system shell).
        cwd: Working directory for the command. Empty means current directory.
        timeout: Maximum seconds to wait before killing the process.
        env_vars: Extra environment variables as KEY=VALUE pairs separated by spaces (e.g. 'DEBUG=1 PORT=3000').
    """
    lines: list[str] = []

    # Build environment
    env = os.environ.copy()
    if env_vars:
        for pair in env_vars.split():
            if "=" in pair:
                k, v = pair.split("=", 1)
                env[k] = v

    # Resolve working directory
    work_dir: str | None = None
    if cwd:
        work_dir = str(Path(cwd).expanduser().resolve())

    proc = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=work_dir,
        env=env,
    )

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(f"  {line}")
            sys.stdout.flush()
            lines.append(line)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        lines.append(f"\n[killed after {timeout}s timeout]")

    output = "".join(lines).strip()
    rc = proc.returncode
    if not output:
        output = f"(exit code {rc})"
    elif rc != 0:
        output += f"\n(exit code {rc})"
    return output

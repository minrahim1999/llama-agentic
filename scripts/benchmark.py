#!/usr/bin/env python3
"""Benchmark tool-calling accuracy and latency for a running llama-server.

Usage:
    uv run python scripts/benchmark.py
    uv run python scripts/benchmark.py --model my-model-name
    uv run python scripts/benchmark.py --url http://localhost:8080/v1
"""

import argparse
import json
import time
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
from rich.console import Console
from rich.table import Table
from rich import print as rprint

# ── Test cases ────────────────────────────────────────────────────────────────
# Each case: prompt, expected_tool (None = no tool expected), optional check_fn

TEST_CASES = [
    {
        "id": "list_dir",
        "prompt": "List the files in the current directory '.'",
        "expected_tool": "list_dir",
        "check_args": lambda a: a.get("path") is not None,
    },
    {
        "id": "read_file",
        "prompt": "Read the file CLAUDE.md",
        "expected_tool": "read_file",
        "check_args": lambda a: "CLAUDE.md" in (a.get("path") or ""),
    },
    {
        "id": "run_python",
        "prompt": "Use Python to compute the square root of 144",
        "expected_tool": "run_python",
        "check_args": lambda a: "144" in (a.get("code") or ""),
    },
    {
        "id": "run_shell",
        "prompt": "Run the shell command: echo hello",
        "expected_tool": "run_shell",
        "check_args": lambda a: "echo" in (a.get("command") or ""),
    },
    {
        "id": "web_search",
        "prompt": "Search the web for 'llama.cpp latest release'",
        "expected_tool": "web_search",
        "check_args": lambda a: a.get("query") is not None,
    },
    {
        "id": "save_memory",
        "prompt": "Remember that the project name is llama-agentic. Save it to memory with key 'project_name'.",
        "expected_tool": "save_memory",
        "check_args": lambda a: a.get("key") == "project_name",
    },
    {
        "id": "edit_file",
        "prompt": "Edit the file test.txt: replace 'hello' with 'world'",
        "expected_tool": "edit_file",
        "check_args": lambda a: a.get("path") is not None and a.get("old_string") is not None,
    },
    {
        "id": "no_tool_math",
        "prompt": "What is 7 times 8?",
        "expected_tool": None,  # should answer directly
        "check_args": None,
    },
    {
        "id": "no_tool_fact",
        "prompt": "What programming language is Python?",
        "expected_tool": None,
        "check_args": None,
    },
]


# ── Tool schemas (minimal, for benchmark) ─────────────────────────────────────

def _schemas():
    # Import the real registry
    import agent.tools.file      # noqa
    import agent.tools.shell     # noqa
    import agent.tools.code      # noqa
    import agent.tools.search    # noqa
    import agent.tools.memory    # noqa
    import agent.tools.edit      # noqa
    from agent.tools import get_all_schemas
    return get_all_schemas()


# ── Parser helpers ────────────────────────────────────────────────────────────

def _extract_tool_call(response_text: str) -> tuple[str | None, dict]:
    """Extract (tool_name, args) from content-embedded tool calls."""
    import re
    patterns = [
        re.compile(r"```(?:json|xml)?\s*\n?(.*?)\n?```", re.DOTALL),
        re.compile(r"<function[_ ]?calls?>\s*(.*?)\s*</function[_ ]?calls?>", re.DOTALL | re.IGNORECASE),
        re.compile(r'\{[^{}]*"name"\s*:\s*"[^"]+".+?\}', re.DOTALL),
    ]
    for pat in patterns:
        for m in pat.finditer(response_text):
            raw = re.sub(r"<[^>]+>", "", m.group(1) if pat.groups else m.group(0)).strip()
            try:
                data = json.loads(raw)
                name = data.get("name") or data.get("function")
                args = data.get("arguments") or data.get("parameters") or {}
                if name:
                    return name, args
            except Exception:
                pass
    return None, {}


# ── Runner ────────────────────────────────────────────────────────────────────

def run_benchmark(server_url: str, model: str) -> list[dict]:
    client = OpenAI(base_url=server_url, api_key="not-required")
    schemas = _schemas()
    results = []

    for case in TEST_CASES:
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an AI assistant with tools. Use tools when asked."},
                    {"role": "user", "content": case["prompt"]},
                ],
                tools=schemas,
                tool_choice="auto",
                stream=False,
                timeout=30,
            )
            elapsed = time.perf_counter() - t0
            msg = resp.choices[0].message
            content = msg.content or ""

            # Determine called tool
            called_tool = None
            called_args: dict = {}
            if msg.tool_calls:
                tc = msg.tool_calls[0]
                called_tool = tc.function.name
                try:
                    called_args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    called_args = {}
            else:
                called_tool, called_args = _extract_tool_call(content)

            expected = case["expected_tool"]
            check_fn = case.get("check_args")

            tool_match = (called_tool == expected)
            args_ok = True
            if tool_match and check_fn and called_args:
                args_ok = check_fn(called_args)

            if expected is None:
                # Should NOT call a tool
                passed = called_tool is None
                status = "PASS" if passed else "WARN"  # warn not fail (model may still answer)
            else:
                passed = tool_match and args_ok
                status = "PASS" if passed else "FAIL"

            results.append({
                "id": case["id"],
                "status": status,
                "expected": expected or "(none)",
                "called": called_tool or "(none)",
                "args_ok": args_ok,
                "latency_s": round(elapsed, 2),
            })

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            results.append({
                "id": case["id"],
                "status": "ERROR",
                "expected": case["expected_tool"] or "(none)",
                "called": f"ERROR: {exc}",
                "args_ok": False,
                "latency_s": round(elapsed, 2),
            })

    return results


def print_results(results: list[dict], model: str):
    console = Console()
    table = Table(title=f"Benchmark — {model}", show_lines=True)
    table.add_column("Test", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Expected tool")
    table.add_column("Called tool")
    table.add_column("Args OK", justify="center")
    table.add_column("Latency (s)", justify="right")

    status_style = {"PASS": "green", "FAIL": "red", "WARN": "yellow", "ERROR": "red bold"}
    passes = 0

    for r in results:
        st = r["status"]
        if st == "PASS":
            passes += 1
        table.add_row(
            r["id"],
            f"[{status_style.get(st, 'white')}]{st}[/]",
            r["expected"],
            r["called"],
            "✓" if r["args_ok"] else "✗",
            str(r["latency_s"]),
        )

    console.print(table)
    total = len(results)
    avg_latency = sum(r["latency_s"] for r in results) / total if total else 0
    console.print(
        f"\nScore: [bold]{passes}/{total}[/bold]  "
        f"Pass rate: [bold]{100*passes//total}%[/bold]  "
        f"Avg latency: [bold]{avg_latency:.1f}s[/bold]"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark llama-server tool-calling")
    parser.add_argument("--url", default="http://localhost:8080/v1", help="llama-server base URL")
    parser.add_argument("--model", default=None, help="Model name (auto-detects if omitted)")
    args = parser.parse_args()

    # Auto-detect model name
    model = args.model
    if not model:
        try:
            client = OpenAI(base_url=args.url, api_key="not-required")
            models = client.models.list()
            model = models.data[0].id if models.data else "local-model"
            print(f"Auto-detected model: {model}")
        except Exception as e:
            print(f"Could not detect model: {e}")
            model = "local-model"

    print(f"Running {len(TEST_CASES)} benchmark tests against {args.url} ...\n")
    results = run_benchmark(args.url, model)
    print_results(results, model)

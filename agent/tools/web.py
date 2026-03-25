"""Web tools — fetch URL content and system info."""

import os
import platform
import shutil
import sys
from agent.tools import tool


@tool
def fetch_url(url: str, timeout: int = 15) -> str:
    """Fetch the text content of a URL (strips HTML tags).

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.
    """
    try:
        import httpx
    except ImportError:
        return "Error: httpx not installed. Run: pip install httpx"

    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers={
            "User-Agent": "llama-agentic/1.0 (text fetcher)"
        })
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        text = resp.text

        if "html" in content_type:
            text = _strip_html(text)

        return text.strip()
    except Exception as e:
        return f"Error fetching {url}: {e}"


def _strip_html(html: str) -> str:
    import re
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
    import re as _re
    html = _re.sub(r"[ \t]+", " ", html)
    html = _re.sub(r"\n{3,}", "\n\n", html)
    return html


@tool
def system_info() -> str:
    """Return OS, Python version, shell, and installed tool versions."""
    lines = [
        f"OS: {platform.system()} {platform.release()} ({platform.machine()})",
        f"Python: {sys.version.split()[0]}",
        f"Shell: {os.environ.get('SHELL', 'unknown')}",
        f"CWD: {os.getcwd()}",
        f"git: {shutil.which('git') or 'not found'}",
    ]

    from agent.config import config
    bin_path = shutil.which(config.llama_server_bin)
    lines.append(f"llama-server: {bin_path or 'not found'}")

    key_pkgs = ["openai", "rich", "click", "pydantic_settings", "httpx", "huggingface_hub", "duckduckgo_search"]
    pkg_vers = []
    for pkg in key_pkgs:
        try:
            mod = __import__(pkg)
            ver = getattr(mod, "__version__", "?")
            pkg_vers.append(f"{pkg}=={ver}")
        except ImportError:
            pkg_vers.append(f"{pkg}=NOT INSTALLED")
    lines.append("Packages: " + ", ".join(pkg_vers))

    return "\n".join(lines)

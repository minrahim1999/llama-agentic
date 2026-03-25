"""Web search tool using DuckDuckGo (no API key required)."""

from agent.tools import tool


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return a summary of results.

    Args:
        query: Search query string.
        max_results: Number of results to return.
    """
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                title = r.get("title", "")
                href = r.get("href", "")
                body = r.get("body", "")
                results.append(f"**{title}**\n{href}\n{body}")
        return "\n\n---\n\n".join(results) if results else "No results found."
    except Exception as exc:
        return f"Search failed: {exc}"

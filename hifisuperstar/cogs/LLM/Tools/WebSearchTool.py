#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from langchain_core.tools import tool

_REQUEST_TIMEOUT = 10  # seconds
_MAX_PAGE_CHARS = 4000


@tool
def web_search(query: str) -> str:
    """Search the web via DuckDuckGo given a search query. Returns a list of result titles, URLs, and snippets."""
    try:
        results = DDGS().text(query, region="wt-wt", safesearch="Moderate", max_results=8)
        if not results:
            return "No results found."
        return "\n\n".join(
            f"{r['title']}\n{r['href']}\n{r['body']}" for r in results
        )
    except Exception as exc:
        return f"Web search failed: {exc}"


@tool
def web_fetch(url: str) -> str:
    """Fetch a webpage by URL and return its readable text content (e.g. to read an article found via web_search)."""
    try:
        response = httpx.get(
            url,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; HifiSuperstarBot/1.0)"},
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception as exc:
        return f"Failed to fetch '{url}': {exc}"

    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())
    if not text:
        return f"No readable text content found at '{url}'."

    if len(text) > _MAX_PAGE_CHARS:
        text = text[:_MAX_PAGE_CHARS] + "... (truncated)"

    return text

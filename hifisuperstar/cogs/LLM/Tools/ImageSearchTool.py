#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from langchain_core.tools import tool
from ddgs import DDGS


@tool
def search_images(query: str) -> str:
    """Search for images on DuckDuckGo given a search query. Returns a list of image titles and URLs."""
    try:
        results = DDGS().images(
            query,
            region='wt-wt',
            safesearch='Moderate',
            timelimit=None,
            max_results=5,
        )
        if not results:
            return 'No images found.'
        return '\n'.join(f"{r['title']}: {r['image']}" for r in results)
    except Exception as exc:
        return f'Image search failed: {exc}'

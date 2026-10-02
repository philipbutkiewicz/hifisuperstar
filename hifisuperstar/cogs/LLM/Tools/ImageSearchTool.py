#
# Hifi Superstar Discord Bot
# Copyright (c) 2021 - 2026 by Philip Butkiewicz and contributors <https://github.com/philipbutkiewicz>
#

from ddgs import DDGS
from langchain_core.tools import tool


def create_image_search_tool(safesearch):
    @tool
    def search_images(query: str) -> str:
        """Search for images on DuckDuckGo given a search query. Returns a list of image titles and URLs."""
        try:
            results = DDGS().images(
                query,
                region="wt-wt",
                safesearch=safesearch,
                timelimit=None,
                max_results=5,
            )
            if not results:
                return "No images found."
            return "\n".join(
                f"{result['title']}: {result['image']}" for result in results
            )
        except Exception as exc:
            return f"Image search failed: {exc}"

    return search_images

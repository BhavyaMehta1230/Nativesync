from ddgs import DDGS


def web_search(query, max_results=5):
    """Searches the web and returns a list of {title, snippet, url} results."""
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                })
    except Exception:
        pass
    return results


def format_search_context(results):
    """Turns search results into a block of text to feed into the AI prompt."""
    if not results:
        return ""
    lines = ["REAL, CURRENT INFORMATION FROM THE WEB — use these actual facts, do not invent different ones:"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}: {r['snippet']}")
    return "\n".join(lines)
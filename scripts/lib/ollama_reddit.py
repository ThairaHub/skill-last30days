"""Ollama client for Reddit discovery (produces results, Claude supervises)."""

import json
import re
import sys
from typing import Any, Dict, List, Optional

from . import http


def _log_error(msg: str):
    """Log error to stderr."""
    sys.stderr.write(f"[OLLAMA/REDDIT ERROR] {msg}\n")
    sys.stderr.flush()


def _log_info(msg: str):
    """Log info to stderr."""
    sys.stderr.write(f"[OLLAMA/REDDIT] {msg}\n")
    sys.stderr.flush()


# Depth configurations: (min, max) threads to request
DEPTH_CONFIG = {
    "quick": (15, 25),
    "default": (30, 50),
    "deep": (70, 100),
}

REDDIT_SEARCH_PROMPT = """Find Reddit discussion threads about: {topic}

STEP 1: EXTRACT THE CORE SUBJECT
Get the MAIN NOUN/PRODUCT/TOPIC:
- "best nano banana prompting practices" → "nano banana"
- "killer features of clawdbot" → "clawdbot"
- "top Claude Code skills" → "Claude Code"
DO NOT include "best", "top", "tips", "practices", "features" in your search.

STEP 2: SEARCH BROADLY
Search for the core subject:
1. "[core subject] site:reddit.com"
2. "reddit [core subject]"
3. "[core subject] reddit"

Return as many relevant threads as you find. We filter by date server-side.

STEP 3: INCLUDE ALL MATCHES
- Include ALL threads about the core subject
- Set date to "YYYY-MM-DD" if you can determine it, otherwise null
- We verify dates and filter old content server-side
- DO NOT pre-filter aggressively - include anything relevant

REQUIRED: URLs must contain "/r/" AND "/comments/"
REJECT: developers.reddit.com, business.reddit.com

Find {min_items}-{max_items} threads. Return MORE rather than fewer.

Return JSON:
{{
  "items": [
    {{
      "title": "Thread title",
      "url": "https://www.reddit.com/r/sub/comments/xyz/title/",
      "subreddit": "subreddit_name",
      "date": "YYYY-MM-DD or null",
      "why_relevant": "Why relevant",
      "relevance": 0.85
    }}
  ]
}}"""


def search_reddit(
    base_url: str,
    model: str,
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    max_items_cap: Optional[int] = None,
) -> Dict[str, Any]:
    """Search Reddit using Ollama.

    Args:
        base_url: Ollama base URL (e.g., "http://localhost:11434")
        model: Ollama model name
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        depth: Research depth - "quick", "default", or "deep"

    Returns:
        Raw response dict with "output" key containing the model's response
    """
    min_items, max_items = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["default"])
    if max_items_cap is not None:
        min_items = min(min_items, max_items_cap)
        max_items = max_items_cap

    prompt = REDDIT_SEARCH_PROMPT.format(
        topic=topic,
        from_date=from_date,
        to_date=to_date,
        min_items=min_items,
        max_items=max_items,
    )

    # Adjust timeout based on depth
    timeout = 90 if depth == "quick" else 120 if depth == "default" else 180

    url = f"{base_url.rstrip('/')}/api/chat"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,  # Lower temperature for more consistent JSON
        }
    }

    headers = {
        "Content-Type": "application/json",
    }

    try:
        response = http.post(url, payload, headers=headers, timeout=timeout)

        # Ollama response format: {"message": {"content": "..."}}
        if isinstance(response, dict):
            message = response.get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "")
                # Return in OpenAI-compatible format
                return {"output": content}

        return {"output": str(response)}
    except http.HTTPError as e:
        _log_error(f"Ollama API error: {e}")
        return {"error": str(e)}


def search_subreddits(
    subreddits: List[str],
    topic: str,
    from_date: str,
    to_date: str,
    count_per: int = 5,
) -> List[Dict[str, Any]]:
    """Search specific subreddits via Reddit's free JSON endpoint.

    No API key needed. Uses reddit.com/r/{sub}/search/.json endpoint.
    Used in Phase 2 supplemental search after entity extraction.

    Args:
        subreddits: List of subreddit names (without r/)
        topic: Search topic
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        count_per: Results to request per subreddit

    Returns:
        List of raw item dicts (same format as parse_reddit_response output).
    """
    all_items = []
    core = _extract_core_subject(topic)

    for sub in subreddits:
        sub = sub.lstrip("r/")
        try:
            url = f"https://www.reddit.com/r/{sub}/search/.json"
            params = f"q={_url_encode(core)}&restrict_sr=on&sort=new&limit={count_per}&raw_json=1"
            full_url = f"{url}?{params}"

            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            }

            data = http.get(full_url, headers=headers, timeout=15, retries=1)

            # Reddit search returns {"data": {"children": [...]}}
            children = data.get("data", {}).get("children", [])
            for i, child in enumerate(children):
                if child.get("kind") != "t3":  # t3 = link/submission
                    continue
                post = child.get("data", {})
                permalink = post.get("permalink", "")
                if not permalink:
                    continue

                item = {
                    "id": f"RS{len(all_items)+1}",
                    "title": str(post.get("title", "")).strip(),
                    "url": f"https://www.reddit.com{permalink}",
                    "subreddit": str(post.get("subreddit", sub)).strip(),
                    "date": None,
                    "why_relevant": f"Found in r/{sub} supplemental search",
                    "relevance": 0.65,  # Slightly lower default for supplemental
                }

                # Parse date from created_utc
                created_utc = post.get("created_utc")
                if created_utc:
                    from . import dates as dates_mod
                    item["date"] = dates_mod.timestamp_to_date(created_utc)

                all_items.append(item)

        except http.HTTPError as e:
            _log_info(f"Subreddit search failed for r/{sub}: {e}")
            if e.status_code == 429:
                _log_info("Reddit rate-limited (429) — skipping remaining subreddits")
                break
        except Exception as e:
            _log_info(f"Subreddit search error for r/{sub}: {e}")

    return all_items


def search_reddit_global(
    topic: str,
    limit: int = 25,
    sort: str = "new",
) -> List[Dict[str, Any]]:
    """Search across all of Reddit using Reddit's global search JSON API.

    This searches ALL subreddits for a topic, without needing an LLM.
    This is the best option for general topics like "infoproducts".

    Args:
        topic: Search topic/query
        limit: Number of results to fetch (default: 25)
        sort: Sort method - "new", "relevance", "hot", "top", "comments" (default: "new")

    Returns:
        List of raw item dicts (same format as parse_reddit_response output).
    """
    items = []
    core = _extract_core_subject(topic)

    try:
        url = "https://www.reddit.com/search.json"
        params = f"q={_url_encode(core)}&sort={sort}&limit={limit}&raw_json=1&type=link"
        full_url = f"{url}?{params}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

        data = http.get(full_url, headers=headers, timeout=15, retries=1)

        # Reddit returns {"data": {"children": [...]}}
        children = data.get("data", {}).get("children", [])
        for i, child in enumerate(children):
            if child.get("kind") != "t3":  # t3 = link/submission
                continue
            post = child.get("data", {})
            permalink = post.get("permalink", "")
            if not permalink:
                continue

            item = {
                "id": f"R{i+1}",
                "title": str(post.get("title", "")).strip(),
                "url": f"https://www.reddit.com{permalink}",
                "subreddit": str(post.get("subreddit", "")).strip(),
                "date": None,
                "why_relevant": f"Found via Reddit search for '{core}'",
                "relevance": 0.75,
            }

            # Parse date from created_utc
            created_utc = post.get("created_utc")
            if created_utc:
                from . import dates as dates_mod
                item["date"] = dates_mod.timestamp_to_date(created_utc)

            items.append(item)

        _log_info(f"Global search found {len(items)} posts for '{core}'")

    except http.HTTPError as e:
        _log_error(f"Failed to search Reddit globally: {e}")
    except Exception as e:
        _log_error(f"Error searching Reddit globally: {e}")

    return items


def fetch_subreddit_posts(
    subreddit: str,
    limit: int = 25,
    sort: str = "new",
) -> List[Dict[str, Any]]:
    """Fetch posts directly from a subreddit using Reddit's JSON API.

    This is a direct fetch without LLM involvement, useful when you want
    real Reddit data instead of LLM hallucinations.

    Args:
        subreddit: Subreddit name (with or without r/)
        limit: Number of posts to fetch (default: 25)
        sort: Sort method - "hot", "new", "top", "rising" (default: "new")

    Returns:
        List of raw item dicts (same format as parse_reddit_response output).
    """
    subreddit = subreddit.lstrip("r/")
    items = []

    try:
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        params = f"limit={limit}&raw_json=1"
        full_url = f"{url}?{params}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

        data = http.get(full_url, headers=headers, timeout=15, retries=1)

        # Reddit returns {"data": {"children": [...]}}
        children = data.get("data", {}).get("children", [])
        for i, child in enumerate(children):
            if child.get("kind") != "t3":  # t3 = link/submission
                continue
            post = child.get("data", {})
            permalink = post.get("permalink", "")
            if not permalink:
                continue

            item = {
                "id": f"R{i+1}",
                "title": str(post.get("title", "")).strip(),
                "url": f"https://www.reddit.com{permalink}",
                "subreddit": str(post.get("subreddit", subreddit)).strip(),
                "date": None,
                "why_relevant": f"Recent post from r/{subreddit}",
                "relevance": 0.70,
            }

            # Parse date from created_utc
            created_utc = post.get("created_utc")
            if created_utc:
                from . import dates as dates_mod
                item["date"] = dates_mod.timestamp_to_date(created_utc)

            items.append(item)

        _log_info(f"Fetched {len(items)} posts from r/{subreddit}")

    except http.HTTPError as e:
        _log_error(f"Failed to fetch r/{subreddit}: {e}")
    except Exception as e:
        _log_error(f"Error fetching r/{subreddit}: {e}")

    return items


def _extract_core_subject(topic: str) -> str:
    """Extract core subject from verbose query for retry."""
    noise = ['best', 'top', 'how to', 'tips for', 'practices', 'features',
             'killer', 'guide', 'tutorial', 'recommendations', 'advice',
             'prompting', 'using', 'for', 'with', 'the', 'of', 'in', 'on']
    words = topic.lower().split()
    result = [w for w in words if w not in noise]
    return ' '.join(result[:3]) or topic  # Keep max 3 words


def _url_encode(text: str) -> str:
    """Simple URL encoding for query parameters."""
    import urllib.parse
    return urllib.parse.quote_plus(text)


def parse_reddit_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse Ollama response to extract Reddit items.

    Args:
        response: Raw API response (same format as OpenAI for compatibility)

    Returns:
        List of item dicts
    """
    items = []

    # Check for API errors first
    if "error" in response and response["error"]:
        error = response["error"]
        err_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        _log_error(f"Ollama API error: {err_msg}")
        if http.DEBUG:
            _log_error(f"Full error response: {json.dumps(response, indent=2)[:1000]}")
        return items

    # Get output text
    output_text = response.get("output", "")
    if not output_text:
        _log_info("No output text found in Ollama response")
        return items

    # Extract JSON from the response
    json_match = re.search(r'\{[\s\S]*"items"[\s\S]*\}', output_text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            items = data.get("items", [])
        except json.JSONDecodeError as e:
            _log_error(f"Failed to parse JSON: {e}")
            return []

    # Validate and clean items
    clean_items = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        url = item.get("url", "")
        if not url or "reddit.com" not in url:
            continue

        clean_item = {
            "id": f"R{i+1}",
            "title": str(item.get("title", "")).strip(),
            "url": url,
            "subreddit": str(item.get("subreddit", "")).strip().lstrip("r/"),
            "date": item.get("date"),
            "why_relevant": str(item.get("why_relevant", "")).strip(),
            "relevance": min(1.0, max(0.0, float(item.get("relevance", 0.5)))),
        }

        # Validate date format
        if clean_item["date"]:
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(clean_item["date"])):
                clean_item["date"] = None

        clean_items.append(clean_item)

    return clean_items

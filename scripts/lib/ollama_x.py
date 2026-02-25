"""Ollama client for X (Twitter) discovery (produces results, Claude supervises)."""

import json
import re
import sys
from typing import Any, Dict, List, Optional

from . import http


def _log_error(msg: str):
    """Log error to stderr."""
    sys.stderr.write(f"[OLLAMA/X ERROR] {msg}\n")
    sys.stderr.flush()


def _log_info(msg: str):
    """Log info to stderr."""
    sys.stderr.write(f"[OLLAMA/X] {msg}\n")
    sys.stderr.flush()


# Depth configurations: (min, max) posts to request
DEPTH_CONFIG = {
    "quick": (8, 12),
    "default": (20, 30),
    "deep": (40, 60),
}

X_SEARCH_PROMPT = """Find X (Twitter) posts about: {topic}

Focus on posts from {from_date} to {to_date}. Find {min_items}-{max_items} high-quality, relevant posts.

IMPORTANT: Return ONLY valid JSON in this exact format, no other text:
{{
  "items": [
    {{
      "text": "Post text content (truncated if long)",
      "url": "https://x.com/user/status/...",
      "author_handle": "username",
      "date": "YYYY-MM-DD or null if unknown",
      "engagement": {{
        "likes": 100,
        "reposts": 25,
        "replies": 15,
        "quotes": 5
      }},
      "why_relevant": "Brief explanation of relevance",
      "relevance": 0.85
    }}
  ]
}}

Rules:
- ONLY include posts you actually found via search. NEVER fabricate or invent URLs, handles, or engagement numbers
- Each status URL must be a real post ID from search results — do NOT generate sequential or placeholder IDs
- relevance is 0.0 to 1.0 (1.0 = highly relevant)
- date must be YYYY-MM-DD format or null
- engagement can be null if unknown
- Include diverse voices/accounts if applicable
- Prefer posts with substantive content, not just links
- If you cannot find real posts, return {{"items": []}} — do NOT make up results"""


def search_x(
    base_url: str,
    model: str,
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    max_items_cap: Optional[int] = None,
) -> Dict[str, Any]:
    """Search X using Ollama.

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

    prompt = X_SEARCH_PROMPT.format(
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
                # Return in xAI-compatible format
                return {"output": content}

        return {"output": str(response)}
    except http.HTTPError as e:
        _log_error(f"Ollama API error: {e}")
        return {"error": str(e)}


def parse_x_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse Ollama response to extract X items.

    Args:
        response: Raw API response (same format as xAI for compatibility)

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
        if not url:
            continue

        # Validate URL is a well-formed X post URL
        if not re.match(r'https?://(x\.com|twitter\.com)/\w+/status/\d+', url):
            continue

        # Parse engagement
        engagement = None
        eng_raw = item.get("engagement")
        if isinstance(eng_raw, dict):
            engagement = {
                "likes": int(eng_raw.get("likes", 0)) if eng_raw.get("likes") else None,
                "reposts": int(eng_raw.get("reposts", 0)) if eng_raw.get("reposts") else None,
                "replies": int(eng_raw.get("replies", 0)) if eng_raw.get("replies") else None,
                "quotes": int(eng_raw.get("quotes", 0)) if eng_raw.get("quotes") else None,
            }

        clean_item = {
            "id": f"X{i+1}",
            "text": str(item.get("text", "")).strip()[:500],  # Truncate long text
            "url": url,
            "author_handle": str(item.get("author_handle", "")).strip().lstrip("@"),
            "date": item.get("date"),
            "engagement": engagement,
            "why_relevant": str(item.get("why_relevant", "")).strip(),
            "relevance": min(1.0, max(0.0, float(item.get("relevance", 0.5)))),
        }

        # Validate date format
        if clean_item["date"]:
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(clean_item["date"])):
                clean_item["date"] = None

        clean_items.append(clean_item)

    return clean_items


def check_ollama_connection(base_url: str, timeout: int = 5) -> bool:
    """Check if Ollama is running and accessible.

    Args:
        base_url: Ollama base URL
        timeout: Request timeout in seconds

    Returns:
        True if Ollama is accessible, False otherwise
    """
    try:
        url = f"{base_url.rstrip('/')}/api/tags"
        headers = {"Accept": "application/json"}
        http.get(url, headers=headers, timeout=timeout)
        return True
    except Exception:
        return False


def list_ollama_models(base_url: str, timeout: int = 5) -> List[str]:
    """List available models from Ollama.

    Args:
        base_url: Ollama base URL
        timeout: Request timeout in seconds

    Returns:
        List of model names
    """
    try:
        url = f"{base_url.rstrip('/')}/api/tags"
        headers = {"Accept": "application/json"}
        response = http.get(url, headers=headers, timeout=timeout)

        if isinstance(response, dict):
            models = response.get("models", [])
            return [m.get("name", "") for m in models if m.get("name")]

        return []
    except Exception as e:
        _log_error(f"Failed to list Ollama models: {e}")
        return []

"""Normalization of raw API data to canonical schema."""

import re
import sys
from typing import Any, Dict, List, TypeVar, Union

from . import dates, schema

T = TypeVar("T", schema.RedditItem, schema.XItem, schema.WebSearchItem, schema.YouTubeItem)


def filter_by_date_range(
    items: List[T],
    from_date: str,
    to_date: str,
    require_date: bool = False,
) -> List[T]:
    """Hard filter: Remove items outside the date range.

    This is the safety net - even if the prompt lets old content through,
    this filter will exclude it.

    Args:
        items: List of items to filter
        from_date: Start date (YYYY-MM-DD) - exclude items before this
        to_date: End date (YYYY-MM-DD) - exclude items after this
        require_date: If True, also remove items with no date

    Returns:
        Filtered list with only items in range (or unknown dates if not required)
    """
    result = []
    for item in items:
        if item.date is None:
            if not require_date:
                result.append(item)  # Keep unknown dates (with scoring penalty)
            continue

        # Hard filter: if date is before from_date, exclude
        if item.date < from_date:
            continue  # DROP - too old

        # Hard filter: if date is after to_date, exclude (likely parsing error)
        if item.date > to_date:
            continue  # DROP - future date

        result.append(item)

    return result


def detect_x_hallucination(items: List[schema.XItem]) -> bool:
    """Detect if a batch of X items was hallucinated by an LLM.

    Checks for signals that indicate fabricated posts:
    - Sequential status IDs (differ by exactly 1)
    - Template IDs (all sharing a long common prefix)
    - All engagement numbers suspiciously round (divisible by 10)

    Args:
        items: Normalized X items to check

    Returns:
        True if hallucination detected (entire batch is suspect).
    """
    if len(items) < 3:
        return False

    # Extract status IDs from URLs
    status_ids = []
    for item in items:
        m = re.search(r'/status/(\d+)', item.url)
        if m:
            status_ids.append(int(m.group(1)))

    if len(status_ids) < 3:
        return False

    # Signal 1: Sequential IDs (3+ IDs differing by exactly 1)
    sorted_ids = sorted(status_ids)
    consecutive = 1
    for i in range(1, len(sorted_ids)):
        if sorted_ids[i] - sorted_ids[i - 1] == 1:
            consecutive += 1
            if consecutive >= 3:
                sys.stderr.write(
                    f"[X HALLUCINATION] Sequential status IDs detected: "
                    f"{sorted_ids[i-2]}..{sorted_ids[i]}\n"
                )
                return True
        else:
            consecutive = 1

    # Signal 2: Template IDs (all share 15+ digit common prefix)
    id_strs = [str(sid) for sid in status_ids]
    prefix_len = 0
    for chars in zip(*id_strs):
        if len(set(chars)) == 1:
            prefix_len += 1
        else:
            break
    if prefix_len >= 15:
        sys.stderr.write(
            f"[X HALLUCINATION] Template IDs detected: "
            f"all {len(id_strs)} IDs share {prefix_len}-digit prefix\n"
        )
        return True

    # Signal 3: All engagement numbers divisible by 10 (4+ items)
    if len(items) >= 4:
        all_round = True
        for item in items:
            if item.engagement is None:
                continue
            eng = item.engagement
            for val in [eng.likes, eng.reposts, eng.replies, eng.quotes]:
                if val is not None and val > 0 and val % 10 != 0:
                    all_round = False
                    break
            if not all_round:
                break
        if all_round:
            sys.stderr.write(
                "[X HALLUCINATION] All engagement numbers are round "
                "(divisible by 10)\n"
            )
            return True

    return False


def normalize_reddit_items(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[schema.RedditItem]:
    """Normalize raw Reddit items to schema.

    Args:
        items: Raw Reddit items from API
        from_date: Start of date range
        to_date: End of date range

    Returns:
        List of RedditItem objects
    """
    normalized = []

    for item in items:
        # Parse engagement
        engagement = None
        eng_raw = item.get("engagement")
        if isinstance(eng_raw, dict):
            engagement = schema.Engagement(
                score=eng_raw.get("score"),
                num_comments=eng_raw.get("num_comments"),
                upvote_ratio=eng_raw.get("upvote_ratio"),
            )

        # Parse comments
        top_comments = []
        for c in item.get("top_comments", []):
            top_comments.append(schema.Comment(
                score=c.get("score", 0),
                date=c.get("date"),
                author=c.get("author", ""),
                excerpt=c.get("excerpt", ""),
                url=c.get("url", ""),
            ))

        # Determine date confidence
        date_str = item.get("date")
        date_confidence = dates.get_date_confidence(date_str, from_date, to_date)

        normalized.append(schema.RedditItem(
            id=item.get("id", ""),
            title=item.get("title", ""),
            url=item.get("url", ""),
            subreddit=item.get("subreddit", ""),
            date=date_str,
            date_confidence=date_confidence,
            engagement=engagement,
            top_comments=top_comments,
            comment_insights=item.get("comment_insights", []),
            relevance=item.get("relevance", 0.5),
            why_relevant=item.get("why_relevant", ""),
        ))

    return normalized


def normalize_x_items(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[schema.XItem]:
    """Normalize raw X items to schema.

    Args:
        items: Raw X items from API
        from_date: Start of date range
        to_date: End of date range

    Returns:
        List of XItem objects
    """
    normalized = []

    for item in items:
        # Parse engagement
        engagement = None
        eng_raw = item.get("engagement")
        if isinstance(eng_raw, dict):
            engagement = schema.Engagement(
                likes=eng_raw.get("likes"),
                reposts=eng_raw.get("reposts"),
                replies=eng_raw.get("replies"),
                quotes=eng_raw.get("quotes"),
            )

        # Determine date confidence
        date_str = item.get("date")
        date_confidence = dates.get_date_confidence(date_str, from_date, to_date)

        normalized.append(schema.XItem(
            id=item.get("id", ""),
            text=item.get("text", ""),
            url=item.get("url", ""),
            author_handle=item.get("author_handle", ""),
            date=date_str,
            date_confidence=date_confidence,
            engagement=engagement,
            relevance=item.get("relevance", 0.5),
            why_relevant=item.get("why_relevant", ""),
        ))

    return normalized


def normalize_youtube_items(
    items: List[Dict[str, Any]],
    from_date: str,
    to_date: str,
) -> List[schema.YouTubeItem]:
    """Normalize raw YouTube items to schema.

    Args:
        items: Raw YouTube items from yt-dlp
        from_date: Start of date range
        to_date: End of date range

    Returns:
        List of YouTubeItem objects
    """
    normalized = []

    for item in items:
        # Parse engagement
        eng_raw = item.get("engagement") or {}
        engagement = schema.Engagement(
            views=eng_raw.get("views"),
            likes=eng_raw.get("likes"),
            num_comments=eng_raw.get("comments"),
        )

        # YouTube dates are reliable (always YYYY-MM-DD from yt-dlp)
        date_str = item.get("date")

        normalized.append(schema.YouTubeItem(
            id=item.get("video_id", ""),
            title=item.get("title", ""),
            url=item.get("url", ""),
            channel_name=item.get("channel_name", ""),
            date=date_str,
            date_confidence="high",
            engagement=engagement,
            transcript_snippet=item.get("transcript_snippet", ""),
            relevance=item.get("relevance", 0.7),
            why_relevant=item.get("why_relevant", ""),
        ))

    return normalized


def items_to_dicts(items: List) -> List[Dict[str, Any]]:
    """Convert schema items to dicts for JSON serialization."""
    return [item.to_dict() for item in items]

"""Safe snippet generation, HTML escaping, and keyword match highlighting."""

import html
import re
from typing import List, Optional, Tuple


class SnippetFormatter:
    """Formats and sanitizes match snippets with HTML markup and highlight extraction.

    Guarantees:
    - Protection against XSS: raw document text is strictly HTML-escaped.
    - Standardized <mark> tags for client highlighting.
    - Deduplicated list of highlighted terms.
    - Fallback snippet generation when FTS snippet is empty or lacks highlights.
    """

    HL_START = "[[[HL]]]"
    HL_END = "[[[/HL]]]"

    @classmethod
    def format(
        cls,
        raw_snippet: Optional[str],
        fallback_content: Optional[str] = None,
        terms: Optional[List[str]] = None,
        max_length: int = 240,
    ) -> Tuple[str, List[str]]:
        """Format a snippet safely into HTML and extract matching terms.

        Args:
            raw_snippet: Raw snippet produced by SQLite FTS5 snippet() using HL markers.
            fallback_content: Original chunk content used if raw snippet is unavailable.
            terms: Query terms used for fallback highlighting.
            max_length: Maximum length for fallback snippets.

        Returns:
            Tuple of (safe_html_snippet, list_of_highlighted_terms).
        """
        if raw_snippet and (cls.HL_START in raw_snippet or cls.HL_END in raw_snippet):
            # 1. Escape HTML in the snippet
            escaped = html.escape(raw_snippet)
            # 2. Replace escaped markers with <mark> and </mark>
            marker_start = html.escape(cls.HL_START)
            marker_end = html.escape(cls.HL_END)
            formatted = escaped.replace(marker_start, "<mark>").replace(marker_end, "</mark>")

            # 3. Extract unique highlighted words
            raw_highlights = re.findall(r"<mark>(.*?)</mark>", formatted, flags=re.IGNORECASE)
            seen = set()
            highlights: List[str] = []
            for h in raw_highlights:
                h_clean = h.strip()
                if h_clean and h_clean.lower() not in seen:
                    seen.add(h_clean.lower())
                    highlights.append(h_clean)

            return formatted, highlights

        # Fallback to building snippet directly from content
        content = fallback_content or raw_snippet or ""
        if not content.strip():
            return "", []

        return cls._create_fallback_snippet(content, terms or [], max_length=max_length)

    @classmethod
    def _create_fallback_snippet(
        cls,
        content: str,
        terms: List[str],
        max_length: int = 240,
    ) -> Tuple[str, List[str]]:
        """Construct a contextual snippet around terms from raw chunk text."""
        escaped_content = html.escape(content.strip())
        if not terms:
            truncated = (
                escaped_content[:max_length] + "..."
                if len(escaped_content) > max_length
                else escaped_content
            )
            return truncated, []

        # Find best match position
        first_pos = -1
        best_term = ""
        for term in terms:
            escaped_term = html.escape(term)
            idx = escaped_content.lower().find(escaped_term.lower())
            if idx != -1 and (first_pos == -1 or idx < first_pos):
                first_pos = idx
                best_term = escaped_term

        if first_pos == -1:
            truncated = (
                escaped_content[:max_length] + "..."
                if len(escaped_content) > max_length
                else escaped_content
            )
            return truncated, []

        # Window around match position
        start = max(0, first_pos - 60)
        end = min(len(escaped_content), start + max_length)
        window = escaped_content[start:end]

        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(escaped_content) else ""
        snippet_text = f"{prefix}{window}{suffix}"

        # Highlight terms inside window
        highlights: List[str] = []
        seen = set()

        for term in terms:
            escaped_term = html.escape(term)
            pattern = re.compile(re.escape(escaped_term), re.IGNORECASE)
            matches = pattern.findall(snippet_text)
            for m in matches:
                if m.lower() not in seen:
                    seen.add(m.lower())
                    highlights.append(m)
            snippet_text = pattern.sub(lambda match: f"<mark>{match.group(0)}</mark>", snippet_text)

        return snippet_text, highlights

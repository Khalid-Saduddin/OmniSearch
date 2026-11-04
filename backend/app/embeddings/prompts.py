"""Task prompt templates and formatting for Google EmbeddingGemma 2."""

from typing import Optional


# Official EmbeddingGemma 2 task prompt prefixes
# SearchQuery task instruction for asymmetric retrieval
QUERY_TASK_PREFIX = "task: search result | query: "

# Document task instruction for corpus chunks
DOCUMENT_DEFAULT_PREFIX = "title: none | text: "


def format_query_prompt(query: str) -> str:
    """Format user search query with the official EmbeddingGemma 2 SearchQuery task instruction.

    Args:
        query: Raw user search query string.

    Returns:
        Formatted query string prefixed with the SearchQuery instruction.
    """
    clean_query = query.strip()
    return f"{QUERY_TASK_PREFIX}{clean_query}"


def format_document_prompt(content: str, title: Optional[str] = None) -> str:
    """Format document chunk with the official EmbeddingGemma 2 Document task instruction.

    Args:
        content: Raw chunk text content.
        title: Optional document or file title.

    Returns:
        Formatted document string with title metadata or default prefix.
    """
    clean_content = content.strip()
    if title and title.strip():
        clean_title = title.strip()
        return f"title: {clean_title} | text: {clean_content}"
    return f"{DOCUMENT_DEFAULT_PREFIX}{clean_content}"


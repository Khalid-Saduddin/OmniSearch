"""OmniSearch search module providing FTS5 keyword, ChromaDB semantic, and RRF hybrid search."""

from app.search.hybrid_search import HybridSearchEngine
from app.search.keyword_search import KeywordSearchEngine
from app.search.query_parser import ParsedQuery, QueryParser
from app.search.rrf import FusedCandidate, ReciprocalRankFusion
from app.search.semantic_search import SemanticSearchEngine
from app.search.snippets import SnippetFormatter

__all__ = [
    "KeywordSearchEngine",
    "SemanticSearchEngine",
    "HybridSearchEngine",
    "ReciprocalRankFusion",
    "FusedCandidate",
    "QueryParser",
    "ParsedQuery",
    "SnippetFormatter",
]

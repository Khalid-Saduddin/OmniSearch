"""Embeddings subsystem for OmniSearch."""

from app.embeddings.base import BaseEmbedder
from app.embeddings.configuration import EmbeddingConfig
from app.embeddings.embedder import EmbeddingGemmaEmbedder
from app.embeddings.exceptions import (
    DimensionMismatchError,
    EmbeddingError,
    InferenceError,
    ModelLoadError,
    ModelNotFoundError,
)
from app.embeddings.model_manager import EmbeddingModelManager
from app.embeddings.prompts import (
    DOCUMENT_DEFAULT_PREFIX,
    QUERY_TASK_PREFIX,
    format_document_prompt,
    format_query_prompt,
)
from app.embeddings.test_embedder import DeterministicTestEmbedder

__all__ = [
    "BaseEmbedder",
    "EmbeddingConfig",
    "EmbeddingGemmaEmbedder",
    "DeterministicTestEmbedder",
    "EmbeddingModelManager",
    "EmbeddingError",
    "ModelNotFoundError",
    "ModelLoadError",
    "InferenceError",
    "DimensionMismatchError",
    "QUERY_TASK_PREFIX",
    "DOCUMENT_DEFAULT_PREFIX",
    "format_query_prompt",
    "format_document_prompt",
]


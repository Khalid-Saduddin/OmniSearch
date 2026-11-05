"""Automated tests for embedding configuration, prompt templates, and embedder interfaces."""

import math
import pytest
from app.embeddings.configuration import EmbeddingConfig
from app.embeddings.exceptions import DimensionMismatchError, ModelNotFoundError
from app.embeddings.model_manager import EmbeddingModelManager
from app.embeddings.prompts import (
    DOCUMENT_DEFAULT_PREFIX,
    QUERY_TASK_PREFIX,
    format_document_prompt,
    format_query_prompt,
)
from app.embeddings.test_embedder import DeterministicTestEmbedder


def test_format_query_prompt():
    """Verify official EmbeddingGemma 2 SearchQuery task instruction formatting."""
    query = "quarterly revenue forecast"
    formatted = format_query_prompt(query)
    assert formatted == f"{QUERY_TASK_PREFIX}quarterly revenue forecast"
    assert formatted.startswith("task: search result | query: ")


def test_format_document_prompt():
    """Verify document chunk formatting with and without title metadata."""
    content = "OmniSearch indexes local documents seamlessly."
    # Without title
    fmt_no_title = format_document_prompt(content)
    assert fmt_no_title == f"{DOCUMENT_DEFAULT_PREFIX}{content}"
    assert fmt_no_title.startswith("title: none | text: ")

    # With title
    fmt_with_title = format_document_prompt(content, title="OmniSearch Architecture")
    assert fmt_with_title == "title: OmniSearch Architecture | text: OmniSearch indexes local documents seamlessly."


def test_embedding_config_dimension_validation():
    """Verify MRL Matryoshka dimension validation."""
    for dim in [768, 512, 256, 128]:
        cfg = EmbeddingConfig(dimension=dim)
        cfg.validate_dimension()  # Should not raise

    with pytest.raises(ValueError, match="Invalid embedding dimension"):
        cfg_invalid = EmbeddingConfig(dimension=384)
        cfg_invalid.validate_dimension()


def test_deterministic_test_embedder_properties():
    """Verify test embedder returns valid unit-length L2-normalized vectors."""
    embedder = DeterministicTestEmbedder(dimension=768)
    assert embedder.dimension == 768
    assert embedder.is_loaded is True

    # Embed query
    vec = embedder.embed_query("machine learning fundamentals")
    assert len(vec) == 768
    # Check L2 norm is ~ 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    assert pytest.approx(norm, abs=1e-4) == 1.0


def test_deterministic_test_embedder_consistency():
    """Verify test embedder produces deterministic vectors for identical inputs."""
    embedder = DeterministicTestEmbedder(dimension=256)
    vec1 = embedder.embed_query("deep neural networks")
    vec2 = embedder.embed_query("deep neural networks")
    assert vec1 == vec2

    # Different text produces different vectors
    vec3 = embedder.embed_query("culinary recipes for dinner")
    assert vec1 != vec3


def test_deterministic_test_embedder_batch_documents():
    """Verify batch document embedding generates matching normalized vectors."""
    embedder = DeterministicTestEmbedder(dimension=512)
    docs = ["First document text", "Second document text", "Third document text"]
    titles = ["Doc 1", "Doc 2", None]

    vectors = embedder.embed_documents(docs, titles=titles)
    assert len(vectors) == 3
    for vec in vectors:
        assert len(vec) == 512
        norm = math.sqrt(sum(x * x for x in vec))
        assert pytest.approx(norm, abs=1e-4) == 1.0


def test_embedding_model_manager_singleton():
    """Verify model manager provides singleton instance and unload mechanics."""
    mgr1 = EmbeddingModelManager.get_instance()
    mgr2 = EmbeddingModelManager.get_instance()
    assert mgr1 is mgr2

    mgr1.unload()
    assert mgr1.is_loaded is False


def test_embedding_model_manager_missing_model():
    """Verify attempting to load non-existent model raises ModelNotFoundError."""
    mgr = EmbeddingModelManager()
    cfg = EmbeddingConfig(model_id="nonexistent-org/nonexistent-model-xyz-12345", local_files_only=True)
    with pytest.raises(ModelNotFoundError):
        mgr.get_model_and_tokenizer(cfg)

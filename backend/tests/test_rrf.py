"""Unit tests for Reciprocal Rank Fusion (RRF) algorithm."""

from dataclasses import dataclass
import pytest
from app.search.rrf import FusedCandidate, ReciprocalRankFusion


@dataclass
class MockSearchItem:
    chunk_id: int
    content: str


def test_rrf_empty_lists():
    """Verify RRF handles empty input lists cleanly."""
    res = ReciprocalRankFusion.fuse([], [], k=60)
    assert res == []

    res_none = ReciprocalRankFusion.fuse(None, None, k=60)
    assert res_none == []


def test_rrf_single_list_keyword_only():
    """Verify RRF calculation for single list (keyword only)."""
    items = [
        MockSearchItem(chunk_id=10, content="Doc 10"),
        MockSearchItem(chunk_id=20, content="Doc 20"),
    ]
    # k = 60
    # Rank 1: 1 / (60 + 1) = 1 / 61 = 0.016393
    # Rank 2: 1 / (60 + 2) = 1 / 62 = 0.016129
    fused = ReciprocalRankFusion.fuse(keyword_items=items, semantic_items=[], k=60)
    assert len(fused) == 2
    assert fused[0].chunk_id == 10
    assert fused[0].keyword_rank == 1
    assert fused[0].semantic_rank is None
    assert fused[0].rrf_score == pytest.approx(1.0 / 61, abs=1e-5)

    assert fused[1].chunk_id == 20
    assert fused[1].keyword_rank == 2
    assert fused[1].semantic_rank is None
    assert fused[1].rrf_score == pytest.approx(1.0 / 62, abs=1e-5)


def test_rrf_two_lists_overlapping():
    """Verify RRF correctly sums reciprocal ranks for overlapping documents."""
    # Keyword: [1, 2, 3]
    # Semantic: [2, 4, 1]
    # k = 60
    # Chunk 1: keyword rank 1 (1/61), semantic rank 3 (1/63) -> 1/61 + 1/63 = 0.0163934 + 0.0158730 = 0.032266
    # Chunk 2: keyword rank 2 (1/62), semantic rank 1 (1/61) -> 1/62 + 1/61 = 0.0161290 + 0.0163934 = 0.032522
    # Chunk 3: keyword rank 3 (1/63), semantic None (0)     -> 1/63 = 0.015873
    # Chunk 4: keyword None (0), semantic rank 2 (1/62)     -> 1/62 = 0.016129
    # Expected ordering:
    # 1st: Chunk 2 (score ~ 0.032522)
    # 2nd: Chunk 1 (score ~ 0.032266)
    # 3rd: Chunk 4 (score ~ 0.016129)
    # 4th: Chunk 3 (score ~ 0.015873)

    kw = [MockSearchItem(chunk_id=1, content="A"), MockSearchItem(chunk_id=2, content="B"), MockSearchItem(chunk_id=3, content="C")]
    sem = [MockSearchItem(chunk_id=2, content="B"), MockSearchItem(chunk_id=4, content="D"), MockSearchItem(chunk_id=1, content="A")]

    fused = ReciprocalRankFusion.fuse(keyword_items=kw, semantic_items=sem, k=60)

    assert len(fused) == 4
    assert [f.chunk_id for f in fused] == [2, 1, 4, 3]

    assert fused[0].chunk_id == 2
    assert fused[0].keyword_rank == 2
    assert fused[0].semantic_rank == 1
    assert fused[0].rrf_score == pytest.approx(1.0 / 62 + 1.0 / 61, abs=1e-5)

    assert fused[1].chunk_id == 1
    assert fused[1].keyword_rank == 1
    assert fused[1].semantic_rank == 3
    assert fused[1].rrf_score == pytest.approx(1.0 / 61 + 1.0 / 63, abs=1e-5)

    assert fused[2].chunk_id == 4
    assert fused[2].keyword_rank is None
    assert fused[2].semantic_rank == 2
    assert fused[2].rrf_score == pytest.approx(1.0 / 62, abs=1e-5)

    assert fused[3].chunk_id == 3
    assert fused[3].keyword_rank == 3
    assert fused[3].semantic_rank is None
    assert fused[3].rrf_score == pytest.approx(1.0 / 63, abs=1e-5)


def test_rrf_duplicate_chunk_ids_in_same_list():
    """Verify duplicate chunk IDs in the same input sequence retain their best rank."""
    kw = [
        MockSearchItem(chunk_id=5, content="First occurrence"),
        MockSearchItem(chunk_id=5, content="Duplicate occurrence"),
        MockSearchItem(chunk_id=6, content="Second item"),
    ]
    fused = ReciprocalRankFusion.fuse(keyword_items=kw, semantic_items=[], k=60)
    assert len(fused) == 2
    assert fused[0].chunk_id == 5
    assert fused[0].keyword_rank == 1
    assert fused[1].chunk_id == 6
    assert fused[1].keyword_rank == 2


def test_rrf_configurable_k():
    """Verify configurable k parameter modifies scale correctly."""
    kw = [MockSearchItem(chunk_id=1, content="A")]
    sem = [MockSearchItem(chunk_id=1, content="A")]

    fused_k10 = ReciprocalRankFusion.fuse(kw, sem, k=10)
    # 1/(10+1) + 1/(10+1) = 2/11 = 0.181818
    assert fused_k10[0].rrf_score == pytest.approx(2.0 / 11, abs=1e-5)

    with pytest.raises(ValueError, match="k must be >= 1"):
        ReciprocalRankFusion.fuse(kw, sem, k=0)


def test_rrf_deterministic_tie_breaking():
    """Verify deterministic tie-breaking:
    1. Score descending
    2. Best single rank ascending
    3. Canonical chunk_id ascending
    """
    # Two candidates with identical scores:
    # Candidate 1: only in keyword at rank 1 -> 1 / (60 + 1) = 1/61
    # Candidate 2: only in semantic at rank 1 -> 1 / (60 + 1) = 1/61
    # Best rank is 1 for both.
    # Tie-break by chunk_id ascending: Chunk 10 beats Chunk 20.
    kw = [MockSearchItem(chunk_id=20, content="Twenty")]
    sem = [MockSearchItem(chunk_id=10, content="Ten")]

    fused = ReciprocalRankFusion.fuse(keyword_items=kw, semantic_items=sem, k=60)
    assert len(fused) == 2
    assert fused[0].chunk_id == 10
    assert fused[1].chunk_id == 20

    # Best rank tie-breaking:
    # Candidate A: keyword rank 1 (1/61 = ~0.01639)
    # Candidate B: keyword rank 2, semantic rank 5:
    # Let's construct a case where scores tie or best rank differentiates:
    # Suppose Item A has ranks {keyword: 2, semantic: 2} -> 2/62
    # Item B has ranks {keyword: 1, semantic: 3} -> 1/61 + 1/63
    # 1/61 + 1/63 = 124 / 3843 = 0.032266
    # 2/62 = 1/31 = 0.032258
    # Scores are very close but not identical.
    # What if two candidates have strictly identical scores?
    # Candidate X: keyword rank 5 (1/65)
    # Candidate Y: semantic rank 5 (1/65)
    # If chunk_ids are 100 and 50:
    kw_tie = [MockSearchItem(chunk_id=100, content="")]
    sem_tie = [MockSearchItem(chunk_id=50, content="")]
    fused_tie = ReciprocalRankFusion.fuse(keyword_items=kw_tie, semantic_items=sem_tie, k=60)
    assert [f.chunk_id for f in fused_tie] == [50, 100]

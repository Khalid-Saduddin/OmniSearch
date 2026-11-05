"""Reciprocal Rank Fusion (RRF) algorithm for combining lexical and semantic search rankings."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class FusedCandidate:
    """Represents a deduplicated document chunk with fused reciprocal rank scores."""

    chunk_id: int
    rrf_score: float
    ranks: Dict[str, int] = field(default_factory=dict)
    keyword_rank: Optional[int] = None
    semantic_rank: Optional[int] = None
    keyword_item: Optional[Any] = None
    semantic_item: Optional[Any] = None


class ReciprocalRankFusion:
    """Production-grade Reciprocal Rank Fusion (RRF) rank aggregation.

    Formula:
        RRF(d) = SUM_{m in M} (1 / (k + rank_m(d)))

    Properties:
    - Independent of raw score magnitudes (BM25 vs. Cosine Similarity).
    - Configurable constant k (default: 60).
    - Deterministic tie-breaking:
        1. RRF score descending.
        2. Minimum available rank ascending (best single ranking).
        3. Canonical chunk_id ascending (numeric identity).
    - Handles missing ranks, duplicate chunk IDs, and asymmetric/empty result lists.
    """

    DEFAULT_K: int = 60

    @classmethod
    def fuse(
        cls,
        keyword_items: Optional[Sequence[Any]] = None,
        semantic_items: Optional[Sequence[Any]] = None,
        k: int = DEFAULT_K,
    ) -> List[FusedCandidate]:
        """Combine keyword and semantic candidate lists using Reciprocal Rank Fusion.

        Args:
            keyword_items: Ordered sequence of keyword search matches (1-based ranking).
            semantic_items: Ordered sequence of semantic search matches (1-based ranking).
            k: RRF smoothing constant (must be >= 1, default: 60).

        Returns:
            Deduplicated list of FusedCandidate objects sorted by final fused rank.
        """
        if k < 1:
            raise ValueError(f"RRF smoothing constant k must be >= 1, got {k}")

        candidates_map: Dict[int, FusedCandidate] = {}

        # 1. Process keyword candidates (1-based ranks)
        if keyword_items:
            current_rank = 1
            for item in keyword_items:
                cid = getattr(item, "chunk_id", None)
                if cid is None and isinstance(item, dict):
                    cid = item.get("chunk_id")
                if cid is None:
                    continue

                if cid not in candidates_map:
                    candidates_map[cid] = FusedCandidate(
                        chunk_id=cid,
                        rrf_score=0.0,
                        ranks={"keyword": current_rank},
                        keyword_rank=current_rank,
                        keyword_item=item,
                    )
                    current_rank += 1
                elif "keyword" not in candidates_map[cid].ranks:
                    # Item already seen from semantic; record keyword rank
                    candidates_map[cid].ranks["keyword"] = current_rank
                    candidates_map[cid].keyword_rank = current_rank
                    candidates_map[cid].keyword_item = item
                    current_rank += 1
                # If duplicate chunk_id exists within keyword_items, retain its best (first) rank

        # 2. Process semantic candidates (1-based ranks)
        if semantic_items:
            current_rank = 1
            for item in semantic_items:
                cid = getattr(item, "chunk_id", None)
                if cid is None and isinstance(item, dict):
                    cid = item.get("chunk_id")
                if cid is None:
                    continue

                if cid not in candidates_map:
                    candidates_map[cid] = FusedCandidate(
                        chunk_id=cid,
                        rrf_score=0.0,
                        ranks={"semantic": current_rank},
                        semantic_rank=current_rank,
                        semantic_item=item,
                    )
                    current_rank += 1
                elif "semantic" not in candidates_map[cid].ranks:
                    candidates_map[cid].ranks["semantic"] = current_rank
                    candidates_map[cid].semantic_rank = current_rank
                    candidates_map[cid].semantic_item = item
                    current_rank += 1
                # If duplicate chunk_id exists within semantic_items, retain its best (first) rank

        if not candidates_map:
            return []

        # 3. Calculate final RRF scores
        for candidate in candidates_map.values():
            total_rrf = 0.0
            for rank in candidate.ranks.values():
                total_rrf += 1.0 / (k + rank)
            candidate.rrf_score = round(total_rrf, 6)

        # 4. Deterministic sorting:
        #    - RRF score descending
        #    - Minimum available rank ascending (best single engine placement)
        #    - Chunk ID ascending (stable tie-break)
        def sort_key(cand: FusedCandidate):
            min_rank = min(cand.ranks.values()) if cand.ranks else 999999
            return (-cand.rrf_score, min_rank, cand.chunk_id)

        sorted_candidates = sorted(candidates_map.values(), key=sort_key)
        return sorted_candidates

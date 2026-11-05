"""Intelligent document chunking preserving structural boundaries, line numbers, and metadata."""

import re
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger
from app.processing.token_counter import BaseTokenCounter, get_default_token_counter
from app.schemas.extraction import ExtractedDocument, ExtractedSegment, SegmentType
from app.schemas.processing import DocumentChunk

logger = get_logger(__name__)

# Sentence boundary pattern: punctuation followed by space or newline
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+", re.UNICODE)


class DocumentChunker:
    """Splits normalized document content into semantic chunks for vectorization and indexing."""

    def __init__(
        self,
        target_tokens: int = 500,
        overlap_tokens: int = 80,
        token_counter: Optional[BaseTokenCounter] = None,
    ) -> None:
        if overlap_tokens >= target_tokens:
            raise ValueError("overlap_tokens must be strictly less than target_tokens")

        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
        self.counter = token_counter or get_default_token_counter()

    def chunk_document(self, document: ExtractedDocument) -> List[DocumentChunk]:
        """Convert an ExtractedDocument into an ordered sequence of DocumentChunk objects.

        Args:
            document: Normalized ExtractedDocument instance.

        Returns:
            List of DocumentChunk instances. Empty if document contains no extractable content.
        """
        # Filter non-empty segments
        valid_segments = [s for s in document.segments if s.content and s.content.strip()]
        if not valid_segments:
            return []

        doc_title = document.metadata.get("title") or document.filename
        common_meta: Dict[str, Any] = {
            "filename": document.filename,
            "file_type": document.file_type,
            "doc_title": doc_title,
        }

        # Fast path for short documents: if all segments together fit in target_tokens,
        # return a single chunk without arbitrary splitting.
        full_text = "\n\n".join(s.content for s in valid_segments)
        total_tokens = self.counter.count_tokens(full_text)

        if total_tokens <= self.target_tokens:
            first_seg = valid_segments[0]
            last_seg = valid_segments[-1]
            return [
                DocumentChunk(
                    chunk_index=0,
                    content=full_text,
                    token_count=total_tokens,
                    source_segment_index=first_seg.segment_index,
                    page_number=first_seg.page_number,
                    slide_number=first_seg.slide_number,
                    sheet_name=first_seg.sheet_name,
                    row_number=first_seg.row_number,
                    start_line=first_seg.start_line,
                    end_line=last_seg.end_line or first_seg.end_line,
                    metadata={**common_meta, **first_seg.metadata},
                )
            ]

        # Multi-chunk processing: process segments preserving boundaries
        chunks: List[DocumentChunk] = []

        is_code = document.file_type == "code"

        for segment in valid_segments:
            seg_tokens = self.counter.count_tokens(segment.content)
            seg_is_code = is_code or segment.segment_type == SegmentType.CODE_BLOCK

            if seg_tokens <= self.target_tokens:
                # Segment fits in a single chunk
                chunks.append(
                    DocumentChunk(
                        chunk_index=len(chunks),
                        content=segment.content,
                        token_count=seg_tokens,
                        source_segment_index=segment.segment_index,
                        page_number=segment.page_number,
                        slide_number=segment.slide_number,
                        sheet_name=segment.sheet_name,
                        row_number=segment.row_number,
                        start_line=segment.start_line,
                        end_line=segment.end_line,
                        metadata={**common_meta, **segment.metadata},
                    )
                )
            else:
                # Segment exceeds target_tokens: split into overlapping chunks
                sub_chunks = self._split_large_segment(
                    segment=segment,
                    is_code=seg_is_code,
                    common_meta=common_meta,
                    start_chunk_index=len(chunks),
                )
                chunks.extend(sub_chunks)

        # Re-index chunks strictly from 0 to N-1
        for idx, chunk in enumerate(chunks):
            chunk.chunk_index = idx

        return chunks

    def _split_large_segment(
        self,
        segment: ExtractedSegment,
        is_code: bool,
        common_meta: Dict[str, Any],
        start_chunk_index: int,
    ) -> List[DocumentChunk]:
        """Subdivide an oversized segment using sentence or line boundaries with overlap."""
        if is_code:
            # Code: split strictly on line boundaries to never break statements
            units = segment.content.split("\n")
            separator = "\n"
        else:
            # Text/prose: first attempt splitting by paragraphs, then sentences
            paragraphs = segment.content.split("\n\n")
            units: List[str] = []
            for p in paragraphs:
                p_clean = p.strip()
                if not p_clean:
                    continue
                sentences = _SENTENCE_BOUNDARY.split(p_clean)
                for s in sentences:
                    s_clean = s.strip()
                    if s_clean:
                        units.append(s_clean)
            separator = " "

        if not units:
            return []

        chunks: List[DocumentChunk] = []
        current_units: List[str] = []
        current_tokens = 0
        unit_line_offset = segment.start_line or 1

        for unit in units:
            unit_tokens = self.counter.count_tokens(unit)

            # If single unit is larger than target_tokens (e.g. gigantic line or run-on sentence)
            if unit_tokens > self.target_tokens:
                # Flush current buffer first
                if current_units:
                    chunk_text = separator.join(current_units).strip()
                    if chunk_text:
                        chunks.append(
                            self._create_chunk(
                                text=chunk_text,
                                segment=segment,
                                common_meta=common_meta,
                                index=start_chunk_index + len(chunks),
                                line_offset=unit_line_offset,
                            )
                        )
                    current_units = []
                    current_tokens = 0

                # Fallback: slice long unit into token-sized word blocks
                words = unit.split()
                sub_words: List[str] = []
                sub_tokens = 0
                for w in words:
                    w_tokens = self.counter.count_tokens(w)
                    if sub_tokens + w_tokens > self.target_tokens and sub_words:
                        slice_text = " ".join(sub_words)
                        chunks.append(
                            self._create_chunk(
                                text=slice_text,
                                segment=segment,
                                common_meta=common_meta,
                                index=start_chunk_index + len(chunks),
                                line_offset=unit_line_offset,
                            )
                        )
                        # Overlap: keep tail words
                        tail_words: List[str] = []
                        tail_tokens = 0
                        for tw in reversed(sub_words):
                            tw_t = self.counter.count_tokens(tw)
                            if tail_tokens + tw_t > self.overlap_tokens:
                                break
                            tail_words.insert(0, tw)
                            tail_tokens += tw_t
                        sub_words = tail_words
                        sub_tokens = tail_tokens
                    sub_words.append(w)
                    sub_tokens += w_tokens

                if sub_words:
                    slice_text = " ".join(sub_words)
                    chunks.append(
                        self._create_chunk(
                            text=slice_text,
                            segment=segment,
                            common_meta=common_meta,
                            index=start_chunk_index + len(chunks),
                            line_offset=unit_line_offset,
                        )
                    )
                continue

            # Standard accumulation
            if current_tokens + unit_tokens > self.target_tokens and current_units:
                chunk_text = separator.join(current_units).strip()
                if chunk_text:
                    chunks.append(
                        self._create_chunk(
                            text=chunk_text,
                            segment=segment,
                            common_meta=common_meta,
                            index=start_chunk_index + len(chunks),
                            line_offset=unit_line_offset,
                        )
                    )

                # Overlap: keep tail units up to overlap_tokens
                overlap_units: List[str] = []
                overlap_count = 0
                for prev_unit in reversed(current_units):
                    p_tok = self.counter.count_tokens(prev_unit)
                    if overlap_count + p_tok > self.overlap_tokens:
                        break
                    overlap_units.insert(0, prev_unit)
                    overlap_count += p_tok

                current_units = overlap_units
                current_tokens = overlap_count

            current_units.append(unit)
            current_tokens += unit_tokens

        # Flush remaining buffer
        if current_units:
            chunk_text = separator.join(current_units).strip()
            if chunk_text:
                chunks.append(
                    self._create_chunk(
                        text=chunk_text,
                        segment=segment,
                        common_meta=common_meta,
                        index=start_chunk_index + len(chunks),
                        line_offset=unit_line_offset,
                    )
                )

        return chunks

    def _create_chunk(
        self,
        text: str,
        segment: ExtractedSegment,
        common_meta: Dict[str, Any],
        index: int,
        line_offset: int,
    ) -> DocumentChunk:
        """Create a single DocumentChunk with preserved source locations."""
        tokens = self.counter.count_tokens(text)
        return DocumentChunk(
            chunk_index=index,
            content=text,
            token_count=tokens,
            source_segment_index=segment.segment_index,
            page_number=segment.page_number,
            slide_number=segment.slide_number,
            sheet_name=segment.sheet_name,
            row_number=segment.row_number,
            start_line=segment.start_line,
            end_line=segment.end_line,
            metadata={**common_meta, **segment.metadata},
        )


"""Content processing pipeline combining normalization and intelligent chunking."""

from typing import List, Optional, Tuple
from app.core.config import Settings, get_settings
from app.processing.chunker import DocumentChunker
from app.processing.normalizer import TextNormalizer
from app.schemas.extraction import ExtractedDocument
from app.schemas.processing import DocumentChunk


class ContentProcessingPipeline:
    """End-to-end transformation pipeline from raw extracted documents to clean, chunked records."""

    def __init__(
        self,
        normalizer: Optional[TextNormalizer] = None,
        chunker: Optional[DocumentChunker] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.normalizer = normalizer or TextNormalizer()
        if chunker is not None:
            self.chunker = chunker
        else:
            app_settings = settings or get_settings()
            self.chunker = DocumentChunker(
                target_tokens=app_settings.chunk_target_tokens,
                overlap_tokens=app_settings.chunk_overlap_tokens,
            )

    def process_document(self, document: ExtractedDocument) -> Tuple[ExtractedDocument, List[DocumentChunk]]:
        """Normalize document content and generate structured, persistent-ready chunks.

        Args:
            document: Raw ExtractedDocument from Phase 2 ingestion.

        Returns:
            Tuple of:
            - Normalized ExtractedDocument
            - List of DocumentChunk records
        """
        # 1. Normalize segments while respecting code and table structures
        normalized_segments = [
            self.normalizer.normalize_segment(seg, file_type=document.file_type)
            for seg in document.segments
        ]

        normalized_doc = document.model_copy(update={"segments": normalized_segments})

        # 2. Divide normalized segments into chunks
        chunks = self.chunker.chunk_document(normalized_doc)

        return normalized_doc, chunks

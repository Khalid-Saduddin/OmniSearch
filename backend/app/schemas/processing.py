"""Pydantic schemas for content processing, chunking, and database entities."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IndexJobStatus(str, Enum):
    """Execution status for asynchronous or synchronous indexing jobs."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class DocumentChunk(BaseModel):
    """A granular document chunk optimized for persistent storage and future vector search."""

    chunk_index: int = Field(..., description="0-indexed sequence position of the chunk within the file")
    content: str = Field(..., description="Cleaned, normalized text content of the chunk")
    token_count: int = Field(..., description="Calculated token length approximation")
    source_segment_index: int = Field(default=0, description="Originating segment index from extraction")

    # Granular source-location pointers
    page_number: Optional[int] = Field(default=None, description="1-indexed page number (PDF)")
    slide_number: Optional[int] = Field(default=None, description="1-indexed slide number (PPTX)")
    sheet_name: Optional[str] = Field(default=None, description="Spreadsheet sheet name (XLSX)")
    row_number: Optional[int] = Field(default=None, description="Row number (CSV, XLSX)")
    start_line: Optional[int] = Field(default=None, description="1-indexed starting line number (Code, Text)")
    end_line: Optional[int] = Field(default=None, description="1-indexed ending line number (Code, Text)")

    # Additional contextual metadata (e.g. document title, filename, headings)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Contextual chunk metadata")


class FolderRecord(BaseModel):
    """Database representation of an indexed folder directory."""

    id: Optional[int] = None
    path: str
    enabled: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FileRecord(BaseModel):
    """Database representation of a tracked document file."""

    id: Optional[int] = None
    folder_id: Optional[int] = None
    path: str
    filename: str
    extension: str
    file_type: str
    sha256: Optional[str] = None
    size_bytes: int = 0
    modified_at: str
    indexed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str
    error_message: Optional[str] = None
    metadata_json: str = "{}"


class ChunkRecord(BaseModel):
    """Database representation of a persistent document chunk."""

    id: Optional[int] = None
    file_id: int
    chunk_index: int
    source_segment_index: int
    content: str
    token_count: int
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    metadata_json: str = "{}"


class IndexJobRecord(BaseModel):
    """Database representation of an indexing job lifecycle."""

    id: Optional[int] = None
    status: IndexJobStatus = IndexJobStatus.PENDING
    total_files: int = 0
    processed_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None
    error_message: Optional[str] = None


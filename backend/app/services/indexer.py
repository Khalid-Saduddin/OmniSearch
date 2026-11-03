"""Persistent indexing service coordinating scanning, extraction, processing, and SQLite persistence."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import List, Optional, Set, Union
from app.core.logging import get_logger
from app.database.connection import DatabaseConnectionManager
from app.database.repositories.chunks import ChunkRepository
from app.database.repositories.files import FileRepository
from app.database.repositories.folders import FolderRepository
from app.database.repositories.jobs import JobRepository
from app.ingestion.coordinator import IngestionCoordinator
from app.ingestion.hashing import try_calculate_sha256
from app.ingestion.scanner import FolderScanner
from app.processing.pipeline import ContentProcessingPipeline
from app.schemas.extraction import ExtractionStatus, ScannedFile
from app.schemas.processing import FileRecord, IndexJobRecord, IndexJobStatus

logger = get_logger(__name__)


class IndexingService:
    """Manages the full indexing lifecycle with duplicate prevention, chunk replacement, and fault isolation."""

    def __init__(
        self,
        db: DatabaseConnectionManager,
        scanner: Optional[FolderScanner] = None,
        coordinator: Optional[IngestionCoordinator] = None,
        pipeline: Optional[ContentProcessingPipeline] = None,
    ) -> None:
        self.db = db
        self.scanner = scanner or FolderScanner()
        self.coordinator = coordinator or IngestionCoordinator()
        self.pipeline = pipeline or ContentProcessingPipeline()

    def index_folder(
        self,
        folder_path: Union[str, Path],
        reconcile_deleted: bool = True,
        force_reindex: bool = False,
    ) -> IndexJobRecord:
        """Scan, process, and persist all supported files within a folder.

        Args:
            folder_path: Target directory path on local disk.
            reconcile_deleted: Whether to remove database records for files deleted from disk.
            force_reindex: If True, reprocesses files even if size, mtime, and hash match.

        Returns:
            Final IndexJobRecord reflecting processing metrics and job outcome.
        """
        resolved_folder = Path(folder_path).resolve()
        if not resolved_folder.exists() or not resolved_folder.is_dir():
            raise ValueError(f"Folder path does not exist or is not a directory: {resolved_folder}")

        logger.info("Initiating persistent index for folder: %s", resolved_folder)

        # 1. Discover files via recursive folder scanner
        scan_report = self.scanner.scan(resolved_folder)
        supported_files = scan_report.supported_files

        # 2. Register or fetch folder record and create index job in DB
        with self.db.transaction() as conn:
            folder_record = FolderRepository.get_or_create(conn, str(resolved_folder))
            folder_id = folder_record.id
            assert folder_id is not None
            job_id = JobRepository.create(conn, total_files=len(supported_files))

        processed_count = 0
        successful_count = 0
        failed_count = 0
        skipped_count = 0

        # 3. Process each discovered file with individual fault isolation
        for scanned_file in supported_files:
            file_path = scanned_file.path
            processed_count += 1

            try:
                # Check modification stats
                stat_res = file_path.stat()
                mtime_iso = datetime.fromtimestamp(stat_res.st_mtime, tz=timezone.utc).isoformat()
                file_size = stat_res.st_size

                # Check if file already exists in database
                with self.db.connection() as conn:
                    existing_file = FileRepository.get_by_path(conn, str(file_path))

                # Duplicate / unchanged file detection
                if not force_reindex and existing_file and existing_file.status == ExtractionStatus.SUCCESS.value:
                    if existing_file.size_bytes == file_size and existing_file.modified_at == mtime_iso:
                        # Fast identity match: file unchanged
                        logger.debug("File unchanged, skipping re-indexing: %s", file_path.name)
                        skipped_count += 1
                        with self.db.transaction() as conn:
                            JobRepository.update_progress(
                                conn, job_id, processed_count, successful_count, failed_count, skipped_count
                            )
                        continue

                # File is new or modified: perform Phase 2 extraction
                extracted_doc = self.coordinator.extract_document(scanned_file, compute_hash=True)

                if extracted_doc.extraction_status in (ExtractionStatus.FAILED, ExtractionStatus.UNSUPPORTED):
                    # Record failure status in database and clean any stale chunks
                    logger.warning("Indexing failed for file '%s': %s", file_path.name, extracted_doc.error_message)
                    failed_count += 1

                    failed_record = FileRecord(
                        folder_id=folder_id,
                        path=str(file_path),
                        filename=file_path.name,
                        extension=file_path.suffix.lower(),
                        file_type=extracted_doc.file_type,
                        sha256=extracted_doc.sha256,
                        size_bytes=file_size,
                        modified_at=mtime_iso,
                        status=extracted_doc.extraction_status.value,
                        error_message=extracted_doc.error_message,
                        metadata_json=json.dumps(extracted_doc.metadata),
                    )

                    with self.db.transaction() as conn:
                        saved_file_id = FileRepository.upsert(conn, failed_record)
                        ChunkRepository.delete_by_file_id(conn, saved_file_id)
                        JobRepository.update_progress(
                            conn, job_id, processed_count, successful_count, failed_count, skipped_count
                        )
                    continue

                # Extraction succeeded (or empty document): run Phase 3 processing pipeline
                norm_doc, chunks = self.pipeline.process_document(extracted_doc)

                file_record = FileRecord(
                    folder_id=folder_id,
                    path=str(file_path),
                    filename=file_path.name,
                    extension=file_path.suffix.lower(),
                    file_type=extracted_doc.file_type,
                    sha256=extracted_doc.sha256,
                    size_bytes=file_size,
                    modified_at=mtime_iso,
                    status=extracted_doc.extraction_status.value,
                    error_message=extracted_doc.error_message,
                    metadata_json=json.dumps(norm_doc.metadata),
                )

                # Persist file and chunks atomically in a single transaction
                with self.db.transaction() as conn:
                    saved_file_id = FileRepository.upsert(conn, file_record)
                    # Replace old chunks atomically
                    ChunkRepository.delete_by_file_id(conn, saved_file_id)
                    if chunks:
                        ChunkRepository.insert_chunks(conn, saved_file_id, chunks)

                    successful_count += 1
                    JobRepository.update_progress(
                        conn, job_id, processed_count, successful_count, failed_count, skipped_count
                    )

            except Exception as exc:
                logger.error("Unhandled error processing file '%s': %s", file_path.name, exc, exc_info=True)
                failed_count += 1
                with self.db.transaction() as conn:
                    JobRepository.update_progress(
                        conn, job_id, processed_count, successful_count, failed_count, skipped_count
                    )

        # 4. Deleted file reconciliation (remove database records for files deleted from disk)
        if reconcile_deleted:
            present_paths = {str(f.path) for f in supported_files}
            with self.db.transaction() as conn:
                deleted_paths = FileRepository.delete_missing_in_folder(conn, folder_id, present_paths)
                if deleted_paths:
                    logger.info("Reconciliation removed %d deleted file records from database", len(deleted_paths))

        # 5. Finalize job status
        final_status = (
            IndexJobStatus.COMPLETED if failed_count == 0
            else IndexJobStatus.COMPLETED_WITH_ERRORS
        )
        with self.db.transaction() as conn:
            JobRepository.finish(conn, job_id, final_status)
            final_job = JobRepository.get_by_id(conn, job_id)

        assert final_job is not None
        logger.info(
            "Indexing job #%d finished with status '%s' (Total: %d, Success: %d, Skipped: %d, Failed: %d)",
            job_id,
            final_status.value,
            final_job.total_files,
            final_job.successful_files,
            final_job.skipped_files,
            final_job.failed_files,
        )
        return final_job

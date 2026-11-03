"""Recursive directory scanner for discovering documents while enforcing security exclusions."""

import os
from pathlib import Path
from typing import Optional, Set
from app.core.logging import get_logger
from app.ingestion.file_detector import FileTypeDetector
from app.ingestion.registry import ExtractorRegistry, default_registry
from app.schemas.extraction import ScanReport, ScannedFile

logger = get_logger(__name__)

# Centralized default directories excluded from document scanning
DEFAULT_EXCLUDED_DIRECTORIES: Set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    ".pytest_cache",
    ".next",
    "dist",
    "build",
    "$RECYCLE.BIN",
    "System Volume Information",
}


class FolderScanner:
    """Recursively traverses a local folder structure to identify supported documents safely."""

    def __init__(
        self,
        registry: Optional[ExtractorRegistry] = None,
        excluded_dirs: Optional[Set[str]] = None,
        follow_symlinks: bool = False,
    ) -> None:
        self.registry = registry or default_registry
        self.excluded_dirs = (
            {d.lower() for d in excluded_dirs}
            if excluded_dirs is not None
            else {d.lower() for d in DEFAULT_EXCLUDED_DIRECTORIES}
        )
        self.follow_symlinks = follow_symlinks

    def scan(self, root_path: Path) -> ScanReport:
        """Scan directory recursively and return structured ScanReport.

        Args:
            root_path: Target root directory.

        Returns:
            ScanReport detailing discovered supported files, unsupported files, and errors.
        """
        root = Path(root_path).resolve()
        report = ScanReport(root_path=str(root))

        if not root.exists():
            report.scan_errors.append(f"Root path does not exist: {root}")
            return report

        if not root.is_dir():
            report.scan_errors.append(f"Root path is not a directory: {root}")
            return report

        logger.info("Starting folder scan on root directory: %s", root)

        try:
            for dirpath, dirnames, filenames in os.walk(
                root,
                topdown=True,
                followlinks=self.follow_symlinks,
                onerror=lambda err: self._handle_walk_error(err, report),
            ):
                current_dir = Path(dirpath)

                # Prune excluded directories in-place so os.walk does not descend into them
                pruned = []
                for d in list(dirnames):
                    if d.lower() in self.excluded_dirs or d.startswith("."):
                        dirnames.remove(d)
                        pruned.append(str(current_dir / d))
                if pruned:
                    report.skipped_paths.extend(pruned)

                # Process files in current directory
                for filename in filenames:
                    file_path = current_dir / filename

                    # Skip symlinks if follow_symlinks is False
                    if not self.follow_symlinks and file_path.is_symlink():
                        report.skipped_paths.append(str(file_path))
                        continue

                    try:
                        stat_res = file_path.stat()
                        file_size = stat_res.st_size
                    except (OSError, PermissionError) as exc:
                        report.scan_errors.append(f"Cannot access stat for {file_path}: {exc}")
                        continue

                    report.total_discovered += 1
                    ext = file_path.suffix.lower()
                    is_supported = self.registry.get_extractor_for_extension(ext) is not None
                    detected_type = FileTypeDetector.get_format_category(ext) if is_supported else None

                    scanned_item = ScannedFile(
                        path=file_path,
                        filename=filename,
                        extension=ext,
                        file_size=file_size,
                        is_supported=is_supported,
                        detected_type=detected_type,
                    )

                    if is_supported:
                        report.supported_files.append(scanned_item)
                    else:
                        report.unsupported_files.append(scanned_item)

        except Exception as exc:
            logger.error("Unexpected error traversing '%s': %s", root, exc)
            report.scan_errors.append(f"Scan interrupted by exception: {exc}")

        logger.info(
            "Scan complete for '%s'. Total: %d, Supported: %d, Unsupported: %d, Errors: %d",
            root,
            report.total_discovered,
            len(report.supported_files),
            len(report.unsupported_files),
            len(report.scan_errors),
        )
        return report

    def _handle_walk_error(self, error: OSError, report: ScanReport) -> None:
        """Record directory traversal errors without aborting the scan."""
        logger.warning("Directory traversal permission/access error: %s", error)
        report.scan_errors.append(f"Access error: {error}")

"""Indexer engine coordinating parsing, incremental caching, and query operations."""

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

from oswald.core.codeindex.parser import (
    EXTENSION_TO_LANGUAGE,
    ASTParser,
    UniversalTreeSitterParser,
    detect_language,
)
from oswald.core.codeindex.skeleton import build_repo_skeleton
from oswald.core.codeindex.storage import SQLiteSymbolIndex, SymbolIndexStore
from oswald.core.codeindex.types import FileRecord, Symbol

DEFAULT_EXCLUDE_DIRS = (
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".import_linter_cache",
    ".oswald",
    "node_modules",
    "target",
    "vendor",
    ".zig-cache",
    "zig-out",
    "build",
    "dist",
)

DEFAULT_EXTENSIONS = tuple(EXTENSION_TO_LANGUAGE.keys())


def compute_sha256(content: str) -> str:
    """Compute the hexadecimal SHA-256 digest of a text string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class CodeIndexer:
    """High-level codebase indexing service providing incremental updates and symbol queries."""

    def __init__(
        self,
        repo_root: Path | str,
        store: SymbolIndexStore | None = None,
        parser: ASTParser | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.store: SymbolIndexStore = store or SQLiteSymbolIndex(
            self.repo_root / ".oswald" / "index.db"
        )
        self.parser: ASTParser = parser or UniversalTreeSitterParser()

    def index_file(self, rel_path: str) -> bool:
        """Incrementally index a single file if its content has changed.

        Returns:
            True if the file was newly parsed and stored, False if skipped due to cache hit.
        """
        full_path = self.repo_root / rel_path
        if not full_path.is_file():
            self.store.delete_file(rel_path)
            return False

        try:
            content = full_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return False

        current_hash = compute_sha256(content)
        existing_record = self.store.get_file_record(rel_path)

        if existing_record and existing_record.content_hash == current_hash:
            return False

        symbols = self.parser.parse(rel_path, content)
        lang = detect_language(rel_path) or "unknown"
        record = FileRecord(
            path=rel_path,
            content_hash=current_hash,
            language=lang,
            last_indexed_at=datetime.now(UTC).isoformat(),
        )
        self.store.index_file(record, symbols)
        return True

    def scan_and_update(
        self,
        extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
        exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDE_DIRS,
    ) -> tuple[int, int]:
        """Scan repository files, incrementally re-indexing changes and pruning deletions.

        Returns:
            Tuple of (files_updated, total_active_files).
        """
        disk_files: set[str] = set()
        updated_count = 0

        for root, dirs, files in os.walk(self.repo_root):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                if file.endswith(extensions):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(self.repo_root).as_posix()
                    disk_files.add(rel_path)

                    if self.index_file(rel_path):
                        updated_count += 1

        # Prune deleted files from index
        indexed_files = set(self.store.get_all_indexed_files())
        deleted_files = indexed_files - disk_files
        for deleted_file in deleted_files:
            self.store.delete_file(deleted_file)

        return updated_count, len(disk_files)

    def get_skeleton(self, target_files: list[str] | None = None) -> str:
        """Generate a compressed structural skeleton for the repository or scoped files."""
        symbols = self.store.get_all_symbols()
        return build_repo_skeleton(symbols, target_files)

    def find_symbol(self, name: str) -> list[Symbol]:
        """Find symbol definitions matching an exact identifier."""
        return self.store.get_symbols_by_name(name)

    def get_symbols_in_file(self, rel_path: str) -> list[Symbol]:
        """Retrieve all symbols indexed for a specific file path."""
        return self.store.get_symbols_in_file(rel_path)

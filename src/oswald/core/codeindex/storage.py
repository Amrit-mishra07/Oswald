"""SQLite persistence layer for the codebase symbol index.

Architecture Rules:
    - Pure Python sqlite3 and Pydantic.
    - Zero imports of sqlalchemy or external ORM packages.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from oswald.core.codeindex.types import FileRecord, Symbol, SymbolKind


class SymbolIndexStore(Protocol):
    """Protocol for symbol and file metadata persistence."""

    def index_file(self, record: FileRecord, symbols: list[Symbol]) -> None:
        """Store or update a file record and its extracted symbols atomically."""
        ...

    def get_file_record(self, file_path: str) -> FileRecord | None:
        """Retrieve indexed metadata for a specific file path."""
        ...

    def delete_file(self, file_path: str) -> None:
        """Remove a file and its associated symbols from the index."""
        ...

    def get_symbols_by_name(self, name: str) -> list[Symbol]:
        """Query symbols matching a given bare identifier."""
        ...

    def get_symbols_in_file(self, file_path: str) -> list[Symbol]:
        """Query all symbols defined in a given file."""
        ...

    def get_all_indexed_files(self) -> list[str]:
        """List all indexed file paths in the database."""
        ...

    def get_all_symbols(self) -> list[Symbol]:
        """Retrieve every indexed symbol across the entire repository."""
        ...


class SQLiteSymbolIndex:
    """SQLite-backed symbol index store with WAL-mode concurrency and foreign keys."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._mem_conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.execute("PRAGMA foreign_keys=ON;")
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def close(self) -> None:
        """Close persistent in-memory connection if active."""
        if self._mem_conn is not None:
            self._mem_conn.close()
            self._mem_conn = None

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if self._mem_conn is not None:
            yield self._mem_conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA busy_timeout=5000;")
                conn.execute("PRAGMA foreign_keys=ON;")
                yield conn
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    language TEXT NOT NULL,
                    last_indexed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    qualified_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    docstring_first_line TEXT,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    parent_name TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified_name);
                CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
                """
            )
            conn.commit()

    def index_file(self, record: FileRecord, symbols: list[Symbol]) -> None:
        """Atomically update a file's metadata and replace all its symbols."""
        with self._connection() as conn, conn:
            conn.execute("DELETE FROM symbols WHERE file_path = ?;", (record.path,))
            conn.execute(
                """
                INSERT INTO files (path, content_hash, language, last_indexed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    content_hash=excluded.content_hash,
                    language=excluded.language,
                    last_indexed_at=excluded.last_indexed_at;
                """,
                (record.path, record.content_hash, record.language, record.last_indexed_at),
            )
            if symbols:
                conn.executemany(
                    """
                    INSERT INTO symbols (
                        file_path, name, qualified_name, kind, signature,
                        docstring_first_line, start_line, end_line, parent_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    [
                        (
                            sym.file_path,
                            sym.name,
                            sym.qualified_name,
                            sym.kind.value,
                            sym.signature,
                            sym.docstring_first_line,
                            sym.start_line,
                            sym.end_line,
                            sym.parent_name,
                        )
                        for sym in symbols
                    ],
                )

    def get_file_record(self, file_path: str) -> FileRecord | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT path, content_hash, language, last_indexed_at FROM files WHERE path = ?;",
                (file_path,),
            ).fetchone()
            if not row:
                return None
            return FileRecord(
                path=row["path"],
                content_hash=row["content_hash"],
                language=row["language"],
                last_indexed_at=row["last_indexed_at"],
            )

    def delete_file(self, file_path: str) -> None:
        with self._connection() as conn, conn:
            conn.execute("DELETE FROM files WHERE path = ?;", (file_path,))

    def get_symbols_by_name(self, name: str) -> list[Symbol]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT file_path, name, qualified_name, kind, signature,
                       docstring_first_line, start_line, end_line, parent_name
                FROM symbols WHERE name = ? ORDER BY start_line;
                """,
                (name,),
            ).fetchall()
            return [self._row_to_symbol(row) for row in rows]

    def get_symbols_in_file(self, file_path: str) -> list[Symbol]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT file_path, name, qualified_name, kind, signature,
                       docstring_first_line, start_line, end_line, parent_name
                FROM symbols WHERE file_path = ? ORDER BY start_line;
                """,
                (file_path,),
            ).fetchall()
            return [self._row_to_symbol(row) for row in rows]

    def get_all_indexed_files(self) -> list[str]:
        with self._connection() as conn:
            rows = conn.execute("SELECT path FROM files ORDER BY path;").fetchall()
            return [row["path"] for row in rows]

    def get_all_symbols(self) -> list[Symbol]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT file_path, name, qualified_name, kind, signature,
                       docstring_first_line, start_line, end_line, parent_name
                FROM symbols ORDER BY file_path, start_line;
                """
            ).fetchall()
            return [self._row_to_symbol(row) for row in rows]

    @staticmethod
    def _row_to_symbol(row: sqlite3.Row) -> Symbol:
        return Symbol(
            file_path=row["file_path"],
            name=row["name"],
            qualified_name=row["qualified_name"],
            kind=SymbolKind(row["kind"]),
            signature=row["signature"],
            docstring_first_line=row["docstring_first_line"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            parent_name=row["parent_name"],
        )

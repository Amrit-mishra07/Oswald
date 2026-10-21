"""Core code indexing package.

Responsibility:
    AST parsing, SQLite symbol storage, incremental caching, and skeleton generation.

Forbidden imports:
    Must not import from `oswald.api`, `oswald.workers`, or `oswald.db`.
"""

from oswald.core.codeindex.indexer import CodeIndexer
from oswald.core.codeindex.parser import (
    ASTParser,
    UniversalTreeSitterParser,
    detect_language,
)
from oswald.core.codeindex.skeleton import build_file_skeleton, build_repo_skeleton
from oswald.core.codeindex.storage import SQLiteSymbolIndex, SymbolIndexStore
from oswald.core.codeindex.types import FileRecord, Symbol, SymbolKind

__all__ = [
    "ASTParser",
    "CodeIndexer",
    "FileRecord",
    "SQLiteSymbolIndex",
    "Symbol",
    "SymbolIndexStore",
    "SymbolKind",
    "UniversalTreeSitterParser",
    "build_file_skeleton",
    "build_repo_skeleton",
    "detect_language",
]

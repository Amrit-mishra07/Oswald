"""Data structures and types for the codebase indexing subsystem.

Architecture Rules:
    - Pure Pydantic v2 schemas and Enums.
    - Zero imports of sqlalchemy, db, api, or workers.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableBase(BaseModel):
    """Base model enforcing immutability and strict schema validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SymbolKind(StrEnum):
    """Classification of an indexed code symbol."""

    CLASS = "class"
    STRUCT = "struct"
    INTERFACE = "interface"
    TRAIT = "trait"
    ENUM = "enum"
    TYPE = "type"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    ASYNC_METHOD = "async_method"
    CONSTANT = "constant"


class Symbol(_ImmutableBase):
    """A definition extracted from source code (class, function, method, etc.)."""

    name: str = Field(description="Bare identifier name, e.g. 'LLMClient'")
    qualified_name: str = Field(
        description="Dotted hierarchy path, e.g. 'oswald.core.llm.protocol.LLMClient'"
    )
    kind: SymbolKind = Field(description="Kind of symbol")
    signature: str = Field(description="Normalized callable signature or class header without body")
    docstring_first_line: str | None = Field(
        default=None,
        description="First line summary of docstring if present",
    )
    start_line: int = Field(ge=1, description="1-indexed starting line number in source")
    end_line: int = Field(ge=1, description="1-indexed ending line number in source")
    file_path: str = Field(description="Repository-relative file path")
    parent_name: str | None = Field(
        default=None,
        description="Enclosing parent class or scope name if applicable",
    )


class FileRecord(_ImmutableBase):
    """Metadata record for an indexed file in the repository."""

    path: str = Field(description="Repository-relative file path")
    content_hash: str = Field(description="SHA-256 hash of file content for change detection")
    language: str = Field(default="python", description="Programming language identifier")
    last_indexed_at: str = Field(description="ISO 8601 UTC timestamp of indexing")

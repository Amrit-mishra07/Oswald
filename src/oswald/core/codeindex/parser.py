"""AST parser implementation for codebase symbol extraction.

Architecture Rules:
    - AST symbol extraction with tree-sitter-language-pack.
    - Zero heavy non-standard dependencies.
    - Returns strictly typed Symbol instances.
"""

import re
from pathlib import Path
from typing import Protocol

import tree_sitter_language_pack as tslp
from tree_sitter_language_pack.options import ProcessConfig, StructureItem

from oswald.core.codeindex.types import Symbol, SymbolKind


class ASTParser(Protocol):
    """Protocol for language-specific AST symbol extractors."""

    def parse(self, file_path: str, content: str) -> list[Symbol]:
        """Extract all top-level and class-scoped symbols from source content."""
        ...


def _module_path_to_qualname(file_path: str) -> str:
    """Convert a file path to a dotted module prefix."""
    parts = list(Path(file_path).with_suffix("").parts)
    if parts and parts[0] in ("src", "lib", "pkg"):
        parts = parts[1:]
    return ".".join(parts)


def _clean_doc(text: str | None) -> str | None:
    """Extract the first meaningful line from a raw docstring or comment string."""
    if not text:
        return None
    t = text.strip()
    for w in ('"""', "'''", "///", "//", "---", "--", "/**", "/*", "#"):
        if t.startswith(w):
            t = t[len(w) :]
            break
    t = t.rstrip("*/\"'").strip()
    return t.splitlines()[0].strip() if t else None


_COMMENT_RE = re.compile(r"\s*(?://|#|--).*$")


def _clean_sig(sig: str) -> str:
    """Collapse a multi-line signature to a single clean, language-agnostic declaration line."""
    lines = [line for raw in sig.splitlines() if (line := _COMMENT_RE.sub("", raw).strip())]
    return " ".join(lines).rstrip("{:; ").removesuffix(" end").strip()


EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".rs": "rust",
    ".lua": "lua",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".sh": "bash",
    ".bash": "bash",
}


def detect_language(file_path: str) -> str | None:
    """Identify the programming language for a given file path based on its extension."""
    return EXTENSION_TO_LANGUAGE.get(Path(file_path).suffix.lower())


_KIND_MAP = {
    "Class": SymbolKind.CLASS,
    "Struct": SymbolKind.STRUCT,
    "Interface": SymbolKind.INTERFACE,
    "Trait": SymbolKind.TRAIT,
    "Enum": SymbolKind.ENUM,
    "Module": SymbolKind.TYPE,
}
_CONTAINERS = {"Class", "Struct", "Interface", "Trait", "Enum"}


class UniversalTreeSitterParser:
    """Extracts symbols across supported programming languages using tree-sitter-language-pack."""

    def parse(self, file_path: str, content: str, language: str | None = None) -> list[Symbol]:
        """Parse source content into a list of structured Symbol definitions."""
        lang = language or detect_language(file_path)
        if not lang:
            return []

        try:
            cfg = ProcessConfig(
                language=lang,
                structure=True,
                docstrings=True,
                comments=True,
                diagnostics=True,
            )
            res = tslp.process(content, cfg)
        except (tslp.Error, ValueError, UnicodeDecodeError):
            return []

        prefix = _module_path_to_qualname(file_path)
        err_lines = {d.span.start_line for d in res.diagnostics if d.span}
        docs = {d.associated_item: _clean_doc(d.text) for d in res.docstrings if d.associated_item}
        comments = {c.span.end_line: _clean_doc(c.text) for c in res.comments if c.span}
        symbols: list[Symbol] = []

        def _walk(item: StructureItem, parent: str | None) -> None:
            span = item.span
            if not span or span.start_line in err_lines:
                return

            kind_str = str(item.kind)
            # Skip package/namespace headers with no children (e.g. Java package statements)
            if kind_str in ("Module", "Namespace") and not item.children:
                return

            if kind_str == "Impl":
                sig = item.signature or ""
                target = (
                    item.name
                    or re.sub(r"^impl(\s*<[^>]*>)?\s*", "", sig.split(" for ")[-1]).strip()
                )
                p = target.split("<")[0].split("[")[0].strip() or None
                for c in item.children or []:
                    _walk(c, p)
                return

            if not item.name:
                return

            sig = item.signature or item.name
            is_async = "async" in sig[:60].split()
            if kind_str in ("Function", "Method") or parent:
                kind = (
                    (SymbolKind.ASYNC_METHOD if is_async else SymbolKind.METHOD)
                    if (parent or kind_str == "Method")
                    else (SymbolKind.ASYNC_FUNCTION if is_async else SymbolKind.FUNCTION)
                )
            else:
                kind = _KIND_MAP.get(kind_str, SymbolKind.TYPE)

            doc = (
                docs.get(item.name)
                or _clean_doc(item.doc_comment)
                or comments.get(span.start_line - 1)
            )
            qname = ".".join(filter(None, (prefix, parent, item.name)))
            symbols.append(
                Symbol(
                    name=item.name,
                    qualified_name=qname,
                    kind=kind,
                    signature=_clean_sig(sig),
                    docstring_first_line=doc,
                    start_line=span.start_line + 1,
                    end_line=span.end_line + 1,
                    file_path=file_path,
                    parent_name=parent,
                )
            )
            if kind_str in _CONTAINERS:
                for c in item.children or []:
                    _walk(c, item.name)

        for item in res.structure:
            _walk(item, None)

        return symbols

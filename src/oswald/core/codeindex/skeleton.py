"""Skeleton generator for formatting indexed symbols into compressed prompt context.

Architecture Rules:
    - Pure string formatting and symbol grouping.
    - Zero external dependencies.
"""

from collections import defaultdict

from oswald.core.codeindex.types import Symbol, SymbolKind

CONTAINER_KINDS = {
    SymbolKind.CLASS,
    SymbolKind.STRUCT,
    SymbolKind.INTERFACE,
    SymbolKind.TRAIT,
    SymbolKind.ENUM,
}


def build_file_skeleton(file_path: str, symbols: list[Symbol]) -> str:
    """Format symbols belonging to a single file into a compressed textual outline.

    Example output:
        ## src/oswald/core/llm/protocol.py
          class LLMClient(Protocol):
            async def complete(request: LLMRequest) -> LLMResponse
            # Execute a single LLM completion and return a neutral response.
    """
    if not symbols:
        return f"## {file_path}\n  # (no public symbols declared)"

    lines: list[str] = [f"## {file_path}"]

    # Separate container types and top-level functions/symbols
    containers: list[Symbol] = []
    children_by_parent: dict[str, list[Symbol]] = defaultdict(list)
    top_level_symbols: list[Symbol] = []

    for sym in symbols:
        if sym.kind in CONTAINER_KINDS:
            containers.append(sym)
        elif sym.parent_name:
            children_by_parent[sym.parent_name].append(sym)
        else:
            top_level_symbols.append(sym)

    for container in containers:
        lines.append(f"  {container.signature}")
        if container.docstring_first_line:
            lines.append(f"  # {container.docstring_first_line}")
        for child in children_by_parent[container.name]:
            lines.append(f"    {child.signature}")
            if child.docstring_first_line:
                lines.append(f"    # {child.docstring_first_line}")

    # Render methods whose parent was declared in another file
    rendered_parents = {c.name for c in containers}
    for parent_name, children in children_by_parent.items():
        if parent_name not in rendered_parents:
            lines.append(f"  # [{parent_name}]")
            for child in children:
                lines.append(f"    {child.signature}")
                if child.docstring_first_line:
                    lines.append(f"    # {child.docstring_first_line}")

    for sym in top_level_symbols:
        lines.append(f"  {sym.signature}")
        if sym.docstring_first_line:
            lines.append(f"  # {sym.docstring_first_line}")

    return "\n".join(lines)


def build_repo_skeleton(
    symbols: list[Symbol],
    target_files: list[str] | None = None,
) -> str:
    """Construct an aggregated structural skeleton for the repository or scoped files."""
    if not symbols:
        return ""

    symbols_by_file: dict[str, list[Symbol]] = defaultdict(list)
    for sym in symbols:
        if target_files is None or sym.file_path in target_files:
            symbols_by_file[sym.file_path].append(sym)

    file_blocks: list[str] = []
    for file_path in sorted(symbols_by_file.keys()):
        file_blocks.append(build_file_skeleton(file_path, symbols_by_file[file_path]))

    return "\n\n".join(file_blocks)

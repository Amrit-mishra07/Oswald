"""Unit tests for the codebase indexing subsystem (AST parser, SQLite storage, skeleton, indexer)."""

from pathlib import Path

from oswald.core.codeindex import (
    CodeIndexer,
    FileRecord,
    SQLiteSymbolIndex,
    Symbol,
    SymbolKind,
    UniversalTreeSitterParser,
    build_file_skeleton,
    build_repo_skeleton,
)

SAMPLE_PYTHON_CODE = '''"""Sample module docstring."""

from typing import Protocol


class Greeter(Protocol):
    """Greeting protocol definition."""

    def greet(self, name: str, formal: bool = False) -> str:
        """Return a personalized greeting."""
        ...

    async def async_greet(self, name: str) -> str:
        """Async version of greet."""
        ...


def standalone_helper(x: int, /, y: int = 10, *args: int, flag: bool = True, **kwargs: str) -> int:
    """A complex helper with all argument types."""
    return x + y


async def async_worker(timeout: float = 5.0) -> None:
    # No docstring
    pass
'''


def test_python_ast_parser_extracts_all_symbols() -> None:
    parser = UniversalTreeSitterParser()
    symbols = parser.parse("src/sample.py", SAMPLE_PYTHON_CODE)

    # Class, 2 methods, 2 top-level functions = 5 symbols
    assert len(symbols) == 5

    symbols_by_name = {s.name: s for s in symbols}

    # Class
    greeter = symbols_by_name["Greeter"]
    assert greeter.kind == SymbolKind.CLASS
    assert greeter.signature == "class Greeter(Protocol)"
    assert greeter.docstring_first_line == "Greeting protocol definition."
    assert greeter.qualified_name == "sample.Greeter"
    assert greeter.parent_name is None

    # Method
    greet = symbols_by_name["greet"]
    assert greet.kind == SymbolKind.METHOD
    assert greet.signature == "def greet(self, name: str, formal: bool = False) -> str"
    assert greet.docstring_first_line == "Return a personalized greeting."
    assert greet.parent_name == "Greeter"
    assert greet.qualified_name == "sample.Greeter.greet"

    # Async Method
    async_greet = symbols_by_name["async_greet"]
    assert async_greet.kind == SymbolKind.ASYNC_METHOD
    assert async_greet.signature == "async def async_greet(self, name: str) -> str"
    assert async_greet.parent_name == "Greeter"

    # Complex arguments helper
    helper = symbols_by_name["standalone_helper"]
    assert helper.kind == SymbolKind.FUNCTION
    assert helper.signature == (
        "def standalone_helper(x: int, /, y: int = 10, *args: int, flag: bool = True, **kwargs: str) -> int"
    )
    assert helper.docstring_first_line == "A complex helper with all argument types."

    # Async function
    worker = symbols_by_name["async_worker"]
    assert worker.kind == SymbolKind.ASYNC_FUNCTION
    assert worker.signature == "async def async_worker(timeout: float = 5.0) -> None"
    assert worker.docstring_first_line is None


def test_python_ast_parser_handles_syntax_error() -> None:
    parser = UniversalTreeSitterParser()
    symbols = parser.parse("broken.py", "def broken_syntax(:")
    assert symbols == []


def test_sqlite_storage_index_and_query() -> None:
    store = SQLiteSymbolIndex(":memory:")

    record = FileRecord(
        path="src/app.py",
        content_hash="abc123hash",
        language="python",
        last_indexed_at="2026-10-13T12:00:00Z",
    )
    symbols = [
        Symbol(
            name="App",
            qualified_name="app.App",
            kind=SymbolKind.CLASS,
            signature="class App:",
            docstring_first_line="Main app.",
            start_line=1,
            end_line=10,
            file_path="src/app.py",
            parent_name=None,
        ),
        Symbol(
            name="run",
            qualified_name="app.App.run",
            kind=SymbolKind.METHOD,
            signature="def run(self) -> None",
            docstring_first_line=None,
            start_line=5,
            end_line=9,
            file_path="src/app.py",
            parent_name="App",
        ),
    ]

    store.index_file(record, symbols)

    # Query file record
    fetched_record = store.get_file_record("src/app.py")
    assert fetched_record is not None
    assert fetched_record.content_hash == "abc123hash"
    assert store.get_file_record("nonexistent.py") is None

    # Query symbols by name
    app_syms = store.get_symbols_by_name("App")
    assert len(app_syms) == 1
    assert app_syms[0].name == "App"
    assert app_syms[0].signature == "class App:"

    # Query symbols in file
    file_syms = store.get_symbols_in_file("src/app.py")
    assert len(file_syms) == 2

    # Query all symbols
    all_syms = store.get_all_symbols()
    assert len(all_syms) == 2

    # Query all indexed files
    all_files = store.get_all_indexed_files()
    assert all_files == ["src/app.py"]

    # Re-indexing replaces existing symbols
    new_symbols = [
        Symbol(
            name="NewApp",
            qualified_name="app.NewApp",
            kind=SymbolKind.CLASS,
            signature="class NewApp:",
            docstring_first_line=None,
            start_line=1,
            end_line=5,
            file_path="src/app.py",
            parent_name=None,
        )
    ]
    store.index_file(record, new_symbols)
    assert len(store.get_symbols_in_file("src/app.py")) == 1
    assert store.get_symbols_by_name("App") == []

    # Delete file
    store.delete_file("src/app.py")
    assert store.get_file_record("src/app.py") is None
    assert store.get_symbols_in_file("src/app.py") == []


def test_skeleton_generation() -> None:
    symbols = [
        Symbol(
            name="User",
            qualified_name="models.User",
            kind=SymbolKind.CLASS,
            signature="class User(BaseModel):",
            docstring_first_line="User account model.",
            start_line=1,
            end_line=15,
            file_path="src/models.py",
            parent_name=None,
        ),
        Symbol(
            name="verify",
            qualified_name="models.User.verify",
            kind=SymbolKind.METHOD,
            signature="def verify(self) -> bool",
            docstring_first_line="Verify password.",
            start_line=5,
            end_line=10,
            file_path="src/models.py",
            parent_name="User",
        ),
        Symbol(
            name="create_user",
            qualified_name="services.create_user",
            kind=SymbolKind.FUNCTION,
            signature="def create_user(name: str) -> User",
            docstring_first_line="Factory for users.",
            start_line=1,
            end_line=8,
            file_path="src/services.py",
            parent_name=None,
        ),
    ]

    # Full skeleton
    full_skeleton = build_repo_skeleton(symbols)
    assert "## src/models.py" in full_skeleton
    assert "  class User(BaseModel):" in full_skeleton
    assert "  # User account model." in full_skeleton
    assert "    def verify(self) -> bool" in full_skeleton
    assert "    # Verify password." in full_skeleton
    assert "## src/services.py" in full_skeleton
    assert "  def create_user(name: str) -> User" in full_skeleton

    # Scoped skeleton
    scoped = build_repo_skeleton(symbols, target_files=["src/services.py"])
    assert "## src/services.py" in scoped
    assert "## src/models.py" not in scoped

    # Empty file skeleton
    empty_skel = build_file_skeleton("src/empty.py", [])
    assert "# (no public symbols declared)" in empty_skel


def test_code_indexer_workflow(tmp_path: Path) -> None:
    # Setup temporary repo structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    file_a = src_dir / "mod_a.py"
    file_a.write_text("def func_a() -> str:\n    return 'a'\n", encoding="utf-8")

    db_path = tmp_path / ".oswald" / "index.db"
    store = SQLiteSymbolIndex(db_path)
    indexer = CodeIndexer(repo_root=tmp_path, store=store)

    # Initial scan
    updated, total = indexer.scan_and_update()
    assert updated == 1
    assert total == 1

    # Second scan with no changes (cache hit)
    updated, total = indexer.scan_and_update()
    assert updated == 0
    assert total == 1

    # Modify file
    file_a.write_text("def func_a_v2() -> int:\n    return 42\n", encoding="utf-8")
    updated, total = indexer.scan_and_update()
    assert updated == 1
    assert total == 1
    assert len(indexer.find_symbol("func_a_v2")) == 1
    assert len(indexer.find_symbol("func_a")) == 0

    # Query skeleton
    skeleton = indexer.get_skeleton()
    assert "## src/mod_a.py" in skeleton
    assert "def func_a_v2() -> int" in skeleton

    # Delete file from disk and scan
    file_a.unlink()
    updated, total = indexer.scan_and_update()
    assert updated == 0
    assert total == 0
    assert indexer.get_symbols_in_file("src/mod_a.py") == []

    # Non-existent file direct index
    assert indexer.index_file("does_not_exist.py") is False

    # Unreadable file handling
    bad_file = src_dir / "bad.py"
    bad_file.write_bytes(b"\x80abc invalid utf8")
    assert indexer.index_file("src/bad.py") is False

    # Empty skeleton
    assert build_repo_skeleton([]) == ""

    # Store close
    store.close()


def test_universal_tree_sitter_parser_rust() -> None:
    parser = UniversalTreeSitterParser()
    code = """/// Calculate sum
pub fn add(a: i64, b: i64) -> i64 {
    a + b
}

pub struct Calculator<T> {
    pub precision: T,
}

impl<T> Calculator<T> {
    pub fn compute(&self, x: i64) -> i64 {
        x * 2
    }
}
"""
    symbols = parser.parse("src/math.rs", code)
    assert len(symbols) == 3
    by_name = {s.name: s for s in symbols}

    add_fn = by_name["add"]
    assert add_fn.kind == SymbolKind.FUNCTION
    assert add_fn.signature == "pub fn add(a: i64, b: i64) -> i64"
    assert add_fn.docstring_first_line == "Calculate sum"
    assert add_fn.qualified_name == "math.add"

    calc = by_name["Calculator"]
    assert calc.kind == SymbolKind.STRUCT
    assert calc.signature == "pub struct Calculator<T>"

    comp = by_name["compute"]
    assert comp.kind == SymbolKind.METHOD
    assert comp.parent_name == "Calculator"
    assert comp.qualified_name == "math.Calculator.compute"


def test_universal_tree_sitter_parser_java() -> None:
    parser = UniversalTreeSitterParser()
    code = """package app;

/** Main application */
public class App {
    /** Run application */
    public void run() {
    }
}
"""
    symbols = parser.parse("src/App.java", code)
    assert len(symbols) == 2
    by_name = {s.name: s for s in symbols}

    app_cls = by_name["App"]
    assert app_cls.kind == SymbolKind.CLASS
    assert app_cls.docstring_first_line == "Main application"

    run_fn = by_name["run"]
    assert run_fn.kind == SymbolKind.METHOD
    assert run_fn.parent_name == "App"
    assert run_fn.docstring_first_line == "Run application"


def test_universal_tree_sitter_parser_lua() -> None:
    parser = UniversalTreeSitterParser()
    code = """--- Add two numbers
function add(a, b)
    return a + b
end

local function private_helper()
end

function MathUtils:scale(x, factor)
    return x * factor
end
"""
    symbols = parser.parse("lib/math.lua", code)
    assert len(symbols) == 3
    by_name = {s.name: s for s in symbols}

    add_fn = by_name["add"]
    assert add_fn.kind == SymbolKind.FUNCTION
    assert add_fn.signature == "function add(a, b)"
    assert add_fn.docstring_first_line == "Add two numbers"

    helper_fn = by_name["private_helper"]
    assert helper_fn.kind == SymbolKind.FUNCTION
    assert helper_fn.signature == "local function private_helper()"

    scale_fn = by_name["MathUtils:scale"]
    assert scale_fn.kind == SymbolKind.FUNCTION
    assert scale_fn.signature == "function MathUtils:scale(x, factor)"


def test_universal_tree_sitter_parser_typescript() -> None:
    parser = UniversalTreeSitterParser()
    code = """/** Service doc */
export class AppService {
    /** Fetch data */
    public async fetchData(id: string): Promise<string> {
        return id;
    }
}

export interface UserConfig {
    name: string;
}

export function formatString(s: string): string {
    return s;
}
"""
    symbols = parser.parse("src/service.ts", code)
    assert len(symbols) == 4
    by_name = {s.name: s for s in symbols}

    svc = by_name["AppService"]
    assert svc.kind == SymbolKind.CLASS
    assert svc.docstring_first_line == "Service doc"

    fetch_method = by_name["fetchData"]
    assert fetch_method.kind == SymbolKind.ASYNC_METHOD
    assert fetch_method.parent_name == "AppService"
    assert fetch_method.docstring_first_line == "Fetch data"

    cfg = by_name["UserConfig"]
    assert cfg.kind == SymbolKind.INTERFACE

    fmt = by_name["formatString"]
    assert fmt.kind == SymbolKind.FUNCTION


def test_universal_tree_sitter_parser_unsupported_language() -> None:
    parser = UniversalTreeSitterParser()
    symbols = parser.parse("data.unknown_ext", "foo bar baz")
    assert symbols == []


def test_code_indexer_multi_language(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    src_dir = repo_root / "src"
    src_dir.mkdir()

    # Rust file
    (src_dir / "math.rs").write_text("pub fn add(a: i32) -> i32 { a }", encoding="utf-8")
    # TypeScript file
    (src_dir / "service.ts").write_text("export function runService(): void {}", encoding="utf-8")
    # Java file
    (src_dir / "App.java").write_text(
        "public class App { public void start() {} }", encoding="utf-8"
    )
    # Lua file
    (src_dir / "script.lua").write_text("function setup()\nend", encoding="utf-8")

    store = SQLiteSymbolIndex(repo_root / "index.db")
    indexer = CodeIndexer(repo_root=repo_root, store=store)

    updated, total = indexer.scan_and_update()
    assert updated == 4
    assert total == 4

    # Verify language detection in storage records
    rec_rs = store.get_file_record("src/math.rs")
    assert rec_rs is not None
    assert rec_rs.language == "rust"

    rec_ts = store.get_file_record("src/service.ts")
    assert rec_ts is not None
    assert rec_ts.language == "typescript"

    rec_java = store.get_file_record("src/App.java")
    assert rec_java is not None
    assert rec_java.language == "java"

    rec_lua = store.get_file_record("src/script.lua")
    assert rec_lua is not None
    assert rec_lua.language == "lua"

    # Find symbols across languages
    assert len(indexer.find_symbol("add")) == 1
    assert len(indexer.find_symbol("runService")) == 1
    assert len(indexer.find_symbol("start")) == 1
    assert len(indexer.find_symbol("setup")) == 1

    # Multi-language skeleton
    skeleton = indexer.get_skeleton()
    assert "## src/math.rs" in skeleton
    assert "## src/service.ts" in skeleton
    assert "## src/App.java" in skeleton
    assert "## src/script.lua" in skeleton
    store.close()


def test_multi_line_signature_normalization() -> None:
    parser = UniversalTreeSitterParser()
    code = """def create_llm_client(
    provider: str,
    api_key: str,
    timeout: float = 30.0,
) -> LLMClient:
    return LLMClient()
"""
    symbols = parser.parse("src/client.py", code)
    assert len(symbols) == 1
    sym = symbols[0]
    assert sym.name == "create_llm_client"
    assert (
        sym.signature
        == "def create_llm_client( provider: str, api_key: str, timeout: float = 30.0, ) -> LLMClient"
    )


def test_skeleton_renders_external_parent_methods() -> None:
    symbols = [
        Symbol(
            name="Start",
            qualified_name="handlers.Server.Start",
            kind=SymbolKind.METHOD,
            signature="func (s *Server) Start() error",
            docstring_first_line="Start HTTP listener.",
            start_line=1,
            end_line=5,
            file_path="handlers.go",
            parent_name="Server",
        ),
    ]
    skeleton = build_file_skeleton("handlers.go", symbols)
    assert "## handlers.go" in skeleton
    assert "  # [Server]" in skeleton
    assert "    func (s *Server) Start() error" in skeleton
    assert "    # Start HTTP listener." in skeleton


def test_parser_tolerates_partial_syntax_errors() -> None:
    parser = UniversalTreeSitterParser()
    code = """def valid_func_1() -> int:
    return 1

def broken_syntax(:

def valid_func_2() -> int:
    return 2
"""
    symbols = parser.parse("partial.py", code)
    names = [s.name for s in symbols]
    assert "valid_func_1" in names
    assert "valid_func_2" in names
    assert "broken_syntax" not in names

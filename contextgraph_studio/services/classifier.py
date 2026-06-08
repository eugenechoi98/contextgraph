"""文件分类与语言识别。"""

from pathlib import Path


SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".sql"}
DOC_SUFFIXES = {".md", ".txt", ".rst"}
CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".env"}
ASSET_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf"}


def detect_language(path: Path) -> str:
    """根据后缀推断语言。"""

    mapping = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".kt": "kotlin",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".sql": "sql",
        ".ps1": "powershell",
        ".sh": "shell",
        ".html": "html",
        ".css": "css",
    }
    return mapping.get(path.suffix.lower(), "plain")


def classify_file(path: Path) -> tuple[str, str]:
    """识别文件类型与语言。"""

    lower_parts = {part.lower() for part in path.parts}
    lower_name = path.name.lower()
    suffix = path.suffix.lower()

    if any(part in {"tests", "test", "__tests__"} for part in lower_parts):
        return "test", detect_language(path)
    if any(
        lower_name.endswith(test_suffix)
        for test_suffix in (
            ".test.ts",
            ".spec.ts",
            ".test.tsx",
            ".spec.tsx",
            ".test.js",
            ".spec.js",
            ".test.jsx",
            ".spec.jsx",
            ".test.py",
            ".spec.py",
        )
    ):
        return "test", detect_language(path)
    if any(part in {"docs", "doc"} for part in lower_parts) or suffix in DOC_SUFFIXES:
        return "doc", detect_language(path)
    if any(part in {"schema", "schemas", "migrations"} for part in lower_parts):
        return "schema", detect_language(path)
    if suffix in CONFIG_SUFFIXES:
        return "config", detect_language(path)
    if suffix in SOURCE_SUFFIXES:
        return "source_code", detect_language(path)
    if suffix in ASSET_SUFFIXES:
        return "asset", detect_language(path)
    if "generated" in lower_parts or path.name.endswith(".generated.ts"):
        return "generated", detect_language(path)
    return "unknown", detect_language(path)

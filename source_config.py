import os
from pathlib import Path
from typing import Any, Mapping


DEFAULT_LOCAL_SOURCE_NAMES = (
    "relatorio_leads.zip",
    "leads_weekly.zip",
    "relatorio-leads.zip",
)
MAPPING_ENV_KEY = "ORIGIN_MAPPING_TEXT"
RAW_EXTENSIONS = {".csv", ".xlsx", ".xls", ".zip"}


def find_local_source(root: Path, prefer_suffix: str | None = None) -> Path | None:
    """Find the newest supported private input under a local project root."""
    search_roots = [root / "dados_raw", root]
    candidates: list[Path] = []

    for search_root in search_roots:
        if not search_root.exists():
            continue
        candidates.extend(
            path
            for path in search_root.iterdir()
            if path.is_file()
            and not path.name.startswith("~$")
            and path.suffix.lower() in RAW_EXTENSIONS
        )

    if not candidates:
        return None

    preferred = [path for path in candidates if path.name in DEFAULT_LOCAL_SOURCE_NAMES]
    pool = preferred or candidates
    if prefer_suffix:
        by_suffix = [path for path in pool if path.suffix.lower() == prefer_suffix.lower()]
        if by_suffix:
            pool = by_suffix
    elif any(path.suffix.lower() == ".zip" for path in pool):
        pool = [path for path in pool if path.suffix.lower() == ".zip"]
    return max(
        pool,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def load_mapping_text(
    local_mapping: Path | None,
    secrets: Mapping[str, Any] | None = None,
) -> str:
    """Load origin mapping from deployment config, environment, or local file."""
    if secrets:
        secret_value = secrets.get(MAPPING_ENV_KEY)
        if secret_value:
            return str(secret_value)

    env_value = os.getenv(MAPPING_ENV_KEY)
    if env_value:
        return env_value

    if local_mapping and local_mapping.exists():
        return local_mapping.read_text(encoding="utf-8")

    return ""

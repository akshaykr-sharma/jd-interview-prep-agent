"""
Settings for Prep Kit.

Takes:  environment variables (a local .env is loaded automatically)
Gives:  a `Settings` dataclass via `load_settings()`, and `kit_dir_for()`
        which decides where the kit for one JD is written

Paths:
    PREPKIT_JD_PATH      the JD file (only used by `langgraph dev`; the CLI
                         takes --jd instead)
    PREPKIT_RESUME_PATH  optional resume / profile file in .md or .txt
    PREPKIT_OUTPUT_DIR   root folder for kits, default ./output/kits
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_path(name: str, default: Path | None) -> Path | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    path = Path(raw).expanduser()
    # relative paths in .env are relative to the project folder, not the shell
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


@dataclass(frozen=True)
class Settings:
    ollama_model: str
    ollama_base_url: str
    num_ctx: int
    temperature: float
    jd_path: Path
    resume_path: Path | None
    output_dir: Path
    data_dir: Path

    @property
    def kit_dir(self) -> Path:
        return kit_dir_for(self.output_dir, self.jd_path)

    def with_inputs(self, jd: str | Path | None = None, resume: str | Path | None = None) -> "Settings":
        new = self
        if jd:
            new = replace(new, jd_path=Path(jd).expanduser().resolve())
        if resume:
            new = replace(new, resume_path=Path(resume).expanduser().resolve())
        return new


def slugify(text: str, max_len: int = 60) -> str:
    """'Senior ML Engineer (Remote)' -> 'senior-ml-engineer-remote'"""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "untitled"


def kit_dir_for(output_dir: Path, jd_path: Path) -> Path:
    return output_dir / slugify(jd_path.stem)


def load_settings() -> Settings:
    settings = Settings(
        ollama_model=os.getenv("OLLAMA_MODEL") or "qwen2.5:7b",
        ollama_base_url=os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434",
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX") or 16384),
        temperature=float(os.getenv("OLLAMA_TEMPERATURE") or 0.2),
        jd_path=_env_path("PREPKIT_JD_PATH", PROJECT_ROOT / "samples" / "jd_ml_engineer.md"),
        resume_path=_env_path("PREPKIT_RESUME_PATH", None),
        output_dir=_env_path("PREPKIT_OUTPUT_DIR", PROJECT_ROOT / "output" / "kits"),
        data_dir=_env_path("PREPKIT_DATA_DIR", PROJECT_ROOT / ".prepkit"),
    )
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


def langsmith_enabled() -> bool:
    on = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    return on and bool(os.getenv("LANGSMITH_API_KEY"))

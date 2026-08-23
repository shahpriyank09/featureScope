from __future__ import annotations

import json
import re
from pathlib import Path

from prism.models import AnalysisResult, AnalysisSource, PRReference


class AnalysisCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.results_dir = root / "results"
        self.latest_dir = root / "latest"

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)

    def get(self, cache_key: str) -> AnalysisResult | None:
        path = self.results_dir / f"{self._safe_name(cache_key)}.json"
        return self._read(path)

    def get_latest(self, reference: PRReference) -> AnalysisResult | None:
        path = self.latest_dir / f"{reference.cache_slug}.json"
        result = self._read(path)
        if result:
            return result.model_copy(update={"source": AnalysisSource.CACHE})
        return None

    def put(self, result: AnalysisResult) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.latest_dir.mkdir(parents=True, exist_ok=True)
        payload = result.model_dump_json(indent=2)

        result_path = self.results_dir / f"{self._safe_name(result.pull_request.cache_key)}.json"
        latest_path = self.latest_dir / f"{result.pull_request.reference.cache_slug}.json"
        self._atomic_write(result_path, payload)
        self._atomic_write(latest_path, payload)

    @staticmethod
    def _read(path: Path) -> AnalysisResult | None:
        try:
            return AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)


class FixtureStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self, reference: PRReference) -> AnalysisResult | None:
        path = self.root / f"{reference.cache_slug}.json"
        try:
            result = AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
            return result.model_copy(update={"source": AnalysisSource.FIXTURE})
        except (OSError, ValueError, json.JSONDecodeError):
            return None

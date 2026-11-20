"""Persistent reusable occupation icon template database (data/icon_db/)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.config import ICON_DB_DIR, ICON_TEMPLATES_DIR
from src.icons.features import IconAnalysis, analyze_icon, compute_ncc_similarity


def _ascii_slug(name: str) -> str:
    """Return an ASCII-only deterministic filename prefix (safe across all Windows locales)."""
    digest = hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:10]
    return f"occ_{digest}"


def _imread_unicode(path: Path) -> np.ndarray | None:
    """Read an image safely even when the path contains non-ASCII/CJK characters on Windows."""
    if not path.is_file():
        return None
    buf = np.fromfile(str(path), dtype=np.uint8)
    if buf.size == 0:
        return None
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def _imwrite_unicode(path: Path, img: np.ndarray) -> bool:
    """Write a PNG image safely regardless of Windows locale encoding."""
    ok, encoded = cv2.imencode(".png", img)
    if not ok:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded.tobytes())
    return True


@dataclass
class DbMatch:
    """Result of matching a query icon against the persistent occupation database."""

    matched: bool
    occupation_name: str
    similarity: float
    feature_sim: float
    ncc_sim: float


class IconDatabase:
    """Stores confirmed occupation names & representative templates for cross-video reuse."""

    def __init__(self, db_dir: str | Path = ICON_DB_DIR) -> None:
        self.db_dir = Path(db_dir)
        self.templates_dir = self.db_dir / "templates"
        self.catalog_path = self.db_dir / "catalog.json"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.occupations: dict[str, dict] = {}
        self._cache: dict[str, list[IconAnalysis]] = {}
        self.load()

    def load(self) -> None:
        if self.catalog_path.is_file():
            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            self.occupations = data.get("occupations", {})
        else:
            self.occupations = {}
        self._rebuild_cache()

    def save(self) -> None:
        payload = {"version": 1, "occupations": self.occupations}
        self.catalog_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _rebuild_cache(self) -> None:
        self._cache.clear()
        for occ_name, entry in self.occupations.items():
            analyses: list[IconAnalysis] = []
            for rel_path in entry.get("templates", []):
                p = self.db_dir / rel_path
                img = _imread_unicode(p)
                if img is not None:
                    a = analyze_icon(img)
                    if not a.is_empty:
                        analyses.append(a)
            if analyses:
                self._cache[occ_name] = analyses

    def list_occupations(self) -> list[dict]:
        items = []
        for name, entry in sorted(self.occupations.items()):
            templates = entry.get("templates", [])
            items.append(
                {
                    "name": name,
                    "template_count": len(templates),
                    "representative_template": str(self.db_dir / templates[0]) if templates else "",
                }
            )
        return items

    def upsert_occupation(
        self, name: str, sample_images: list[np.ndarray], max_templates: int = 5
    ) -> None:
        """Save or update up to `max_templates` diverse clean template PNGs for an occupation."""
        clean_name = name.strip()
        if not clean_name or clean_name == "(空位)":
            return

        slug = _ascii_slug(clean_name)
        existing_rels: list[str] = list(self.occupations.get(clean_name, {}).get("templates", []))

        # Keep existing valid templates
        valid_rels = [r for r in existing_rels if (self.db_dir / r).is_file()]
        next_idx = len(valid_rels)

        for img in sample_images:
            if len(valid_rels) >= max_templates:
                break
            a = analyze_icon(img)
            if a.is_empty:
                continue
            rel = f"templates/{slug}_{next_idx:02d}.png"
            out_path = self.db_dir / rel
            if _imwrite_unicode(out_path, a.normalized_bgr):
                valid_rels.append(rel)
                next_idx += 1

        self.occupations[clean_name] = {"templates": valid_rels}
        self.save()
        self._rebuild_cache()

    def rename_occupation(self, old_name: str, new_name: str) -> None:
        if old_name in self.occupations and new_name.strip() and old_name != new_name:
            entry = self.occupations.pop(old_name)
            if new_name in self.occupations:
                merged = list(dict.fromkeys(self.occupations[new_name]["templates"] + entry["templates"]))
                self.occupations[new_name]["templates"] = merged[:6]
            else:
                self.occupations[new_name] = entry
            self.save()
            self._rebuild_cache()

    def match(self, analysis: IconAnalysis, threshold: float = 0.84) -> DbMatch:
        """Match an analyzed icon against all stored templates using combined feature + NCC score."""
        if analysis.is_empty or not self._cache:
            return DbMatch(False, "", 0.0, 0.0, 0.0)

        best_occ = ""
        best_score = -1.0
        best_fsim = 0.0
        best_ncc = 0.0

        for occ_name, tpl_list in self._cache.items():
            for tpl in tpl_list:
                fsim = float(np.dot(analysis.feature_vec, tpl.feature_vec))
                ncc = compute_ncc_similarity(analysis.normalized_bgr, tpl.normalized_bgr)
                # Combined similarity balances invariant feature vector & strict pixel-level NCC
                score = 0.55 * fsim + 0.45 * max(0.0, ncc)
                if score > best_score:
                    best_score = score
                    best_occ = occ_name
                    best_fsim = fsim
                    best_ncc = ncc

        return DbMatch(
            matched=(best_score >= threshold),
            occupation_name=best_occ if best_score >= threshold else "",
            similarity=round(max(0.0, best_score), 4),
            feature_sim=round(max(0.0, best_fsim), 4),
            ncc_sim=round(max(0.0, best_ncc), 4),
        )

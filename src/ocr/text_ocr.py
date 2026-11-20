"""Multilingual OCR engine for Rank, Score, and Team Name (Traditional Chinese, English, Thai).

Uses two lazily cached EasyOCR readers:
1. ['ch_tra', 'en'] for digits, English, Traditional/Simplified Chinese
2. ['th', 'en'] routed automatically when CJK/EN confidence is low or Thai script is suspected
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import cv2
import numpy as np

from src.ocr.rank_badge import classify_rank_badge

_ASCII_CLEAN_RE = re.compile(r"^[A-Za-z0-9_.\-\s]+$")
_THAI_CHAR_RE = re.compile(r"[\u0e00-\u0e7f]")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass(frozen=True)
class OcrFieldResult:
    """Recognized text, confidence score, and diagnostic routing metadata."""

    text: str
    confidence: float
    source: str  # "badge" | "digit_ocr" | "cjk_en" | "th_en" | "empty"
    alt_text: str = ""
    alt_confidence: float = 0.0


def preprocess_for_digits(img: np.ndarray, scale: float = 2.5) -> np.ndarray:
    """Upscale, convert to crisp high-contrast grayscale, and add white margin."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()
    # Mild contrast stretch so brown digits become dark ink on pure white
    up = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # Normalize background toward 255 while preserving crisp anti-aliased strokes
    norm = cv2.normalize(up, None, 0, 255, cv2.NORM_MINMAX)
    padded = cv2.copyMakeBorder(norm, 18, 18, 22, 22, cv2.BORDER_CONSTANT, value=255)
    return padded


def preprocess_for_text(img: np.ndarray, scale: float = 2.2) -> np.ndarray:
    """Upscale and pad a team name crop while preserving fine CJK & Thai diacritics."""
    up = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    padded = cv2.copyMakeBorder(up, 16, 16, 20, 20, cv2.BORDER_CONSTANT, value=(252, 250, 248))
    return padded


class MultilingualOcrEngine:
    """Cached dual-reader EasyOCR wrapper with dedicated digit & multilingual pipelines."""

    def __init__(self, gpu: bool = False) -> None:
        self.gpu = gpu
        self._reader_cjk = None
        self._reader_th = None

    @property
    def reader_cjk(self):
        if self._reader_cjk is None:
            import easyocr

            self._reader_cjk = easyocr.Reader(["ch_tra", "en"], gpu=self.gpu, verbose=False)
        return self._reader_cjk

    @property
    def reader_th(self):
        if self._reader_th is None:
            import easyocr

            self._reader_th = easyocr.Reader(["th", "en"], gpu=self.gpu, verbose=False)
        return self._reader_th

    @staticmethod
    def _merge_detections(results: list) -> tuple[str, float]:
        """Join EasyOCR bounding boxes left-to-right and compute length-weighted confidence."""
        if not results:
            return "", 0.0
        # Sort by leftmost X coordinate
        sorted_res = sorted(results, key=lambda r: float(r[0][0][0]))
        texts: list[str] = []
        weighted_conf = 0.0
        total_chars = 0
        for _, txt, conf in sorted_res:
            clean = str(txt).strip()
            if not clean:
                continue
            texts.append(clean)
            weight = max(1, len(clean))
            weighted_conf += float(conf) * weight
            total_chars += weight
        if total_chars == 0:
            return "", 0.0
        joined = " ".join(texts) if all(_ASCII_CLEAN_RE.match(t) for t in texts) else "".join(texts)
        return joined.strip(), round(weighted_conf / total_chars, 4)

    def read_rank(self, rank_img: np.ndarray) -> tuple[int | None, float, str]:
        """Recognize rank number (supports Top 1-3 medal badges + plain digits 4..999)."""
        badge = classify_rank_badge(rank_img)
        if badge.is_badge and badge.rank is not None:
            return badge.rank, badge.confidence, f"badge:{badge.details}"

        proc = preprocess_for_digits(rank_img, scale=2.6)
        res = self.reader_cjk.readtext(
            proc,
            allowlist="0123456789",
            detail=1,
            paragraph=False,
            text_threshold=0.5,
            low_text=0.3,
        )
        txt, conf = self._merge_detections(res)
        digits = re.sub(r"\D", "", txt)
        if digits:
            val = int(digits)
            if 1 <= val <= 999:
                return val, conf, "digit_ocr"
        return None, 0.0, "digit_ocr_failed"

    def read_score(self, score_img: np.ndarray) -> tuple[int | None, float, str]:
        """Recognize numeric team score."""
        proc = preprocess_for_digits(score_img, scale=2.6)
        res = self.reader_cjk.readtext(
            proc,
            allowlist="0123456789",
            detail=1,
            paragraph=False,
            text_threshold=0.5,
            low_text=0.3,
        )
        txt, conf = self._merge_detections(res)
        digits = re.sub(r"\D", "", txt)
        if digits:
            return int(digits), conf, "digit_ocr"
        return None, 0.0, "digit_ocr_failed"

    def read_team_name(self, name_img: np.ndarray) -> OcrFieldResult:
        """Recognize multilingual team name with automatic CJK/EN <-> Thai/EN routing."""
        proc = preprocess_for_text(name_img, scale=2.2)
        res_cjk = self.reader_cjk.readtext(proc, detail=1, paragraph=False)
        txt_cjk, conf_cjk = self._merge_detections(res_cjk)

        # Fast path: clean ASCII/English name with solid confidence does not need Thai reader
        if txt_cjk and _ASCII_CLEAN_RE.match(txt_cjk) and conf_cjk >= 0.72:
            return OcrFieldResult(text=txt_cjk, confidence=conf_cjk, source="cjk_en")

        # Also evaluate with Thai+English reader to accurately capture Thai team names
        res_th = self.reader_th.readtext(proc, detail=1, paragraph=False)
        txt_th, conf_th = self._merge_detections(res_th)

        has_thai = bool(_THAI_CHAR_RE.search(txt_th))
        has_cjk = bool(_CJK_CHAR_RE.search(txt_cjk))

        # Routing decision:
        # 1. Only choose Thai reader when it genuinely detected Thai script (avoid letting th_en
        #    override English capitalization like GODMODE -> godmode or Bura -> bura).
        # 2. Otherwise prefer CJK/EN reader (which handles Chinese + case-sensitive English better).
        if has_thai and (conf_th >= conf_cjk - 0.03 or (conf_th >= 0.42 and conf_cjk < 0.72)):
            return OcrFieldResult(
                text=txt_th,
                confidence=conf_th,
                source="th_en",
                alt_text=txt_cjk,
                alt_confidence=conf_cjk,
            )

        if txt_cjk:
            return OcrFieldResult(
                text=txt_cjk,
                confidence=conf_cjk,
                source="cjk_en",
                alt_text=txt_th,
                alt_confidence=conf_th,
            )

        if txt_th:
            return OcrFieldResult(
                text=txt_th,
                confidence=conf_th,
                source="th_en",
                alt_text=txt_cjk,
                alt_confidence=conf_cjk,
            )

        return OcrFieldResult(text="", confidence=0.0, source="empty")

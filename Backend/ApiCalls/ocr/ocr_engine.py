"""
Read Indian-script text from photos (signboards, menus, documents) with
Tesseract and its Indian-language models.

Photos vary a lot, so a few preprocessed versions of the image are tried and the
reading with the highest confidence in the chosen script wins. Tesseract's
English-only default can't read Indian scripts, so the language models must be
installed (python scripts/download_tessdata.py, or apt packages on Heroku).
"""
import os
import pathlib
import shutil

import cv2
import numpy as np
import pytesseract

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
LOCAL_TESSDATA = PROJECT_ROOT / "tessdata"

TESSERACT_LANG = {
    "Hindi": "hin", "Bengali": "ben", "Tamil": "tam", "Telugu": "tel", "Gujarati": "guj",
    "Kannada": "kan", "Malayalam": "mal", "Marathi": "mar", "Punjabi": "pan", "Odia": "ori",
}
SCRIPT_RANGE = {
    "Hindi": (0x0900, 0x097F), "Marathi": (0x0900, 0x097F), "Bengali": (0x0980, 0x09FF),
    "Punjabi": (0x0A00, 0x0A7F), "Gujarati": (0x0A80, 0x0AFF), "Odia": (0x0B00, 0x0B7F),
    "Tamil": (0x0B80, 0x0BFF), "Telugu": (0x0C00, 0x0C7F), "Kannada": (0x0C80, 0x0CFF),
    "Malayalam": (0x0D00, 0x0D7F),
}

MIN_QUALITY = 35   # below this, Tesseract is usually forcing the wrong script onto the image
MAX_SIDE = 2000


class OCRUnavailable(RuntimeError):
    pass


def configure_tesseract() -> None:
    cmd = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
    if not cmd and os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if not cmd:
        raise OCRUnavailable("Text recognition isn't installed on the server.")
    pytesseract.pytesseract.tesseract_cmd = cmd
    # Prefer the project's own language models when present (Windows / local dev).
    if (LOCAL_TESSDATA / "mal.traineddata").exists():
        os.environ["TESSDATA_PREFIX"] = str(LOCAL_TESSDATA)


def _variants(img: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    # Tesseract likes text roughly 30+ px tall: upscale small photos, shrink huge ones.
    scale = 1000 / max(h, w) if max(h, w) < 1000 else min(1.0, MAX_SIDE / max(h, w))
    if scale != 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.bilateralFilter(gray, 7, 50, 50)

    def dark_on_light(bw):  # signboards are often light text on a dark board
        return cv2.bitwise_not(bw) if np.mean(bw) < 127 else bw

    _, otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(denoised)
    return [clahe, dark_on_light(otsu), dark_on_light(adaptive)]


def _clean_word(word: str, language: str) -> str:
    """Keep only the chosen script and fix Tesseract's usual look-alike mix-ups."""
    lo, hi = SCRIPT_RANGE[language]
    chars = [ch for ch in word.strip() if lo <= ord(ch) <= hi]
    # The script's digit zero (೦ ౦ ൦ …) misread in place of the anusvara (ಂ ం ം …).
    zero, anusvara = lo + 0x66, lo + 0x02
    for i in range(1, len(chars)):
        if ord(chars[i]) == zero and not (lo + 0x66 <= ord(chars[i - 1]) <= lo + 0x6F):
            chars[i] = chr(anusvara)
    word = "".join(chars)
    return word if any(ch.isalpha() for ch in word) else ""


def _group_rows(words: list[tuple]) -> list[str]:
    """Put loose word boxes (sparse mode) back into text lines, left to right."""
    def overlap(a, b):
        top, bottom = max(a[1], b[1]), min(a[1] + a[2], b[1] + b[2])
        return max(0, bottom - top) / max(1, min(a[2], b[2]))

    rows: list[list[tuple]] = []
    for w in sorted(words):
        row = max(rows, key=lambda r: overlap(r[-1], w), default=None)
        if row is not None and overlap(row[-1], w) > 0.4:
            row.append(w)
        else:
            rows.append([w])
    rows.sort(key=lambda r: r[0][1])
    return [" ".join(x[3] for x in row) for row in rows]


def _read(image: np.ndarray, language: str, psm: int) -> tuple[list[str], float]:
    data = pytesseract.image_to_data(image, lang=TESSERACT_LANG[language], config=f"--oem 1 --psm {psm}",
                                     output_type=pytesseract.Output.DICT)
    words, confs, lines = [], [], {}
    for i, raw in enumerate(data["text"]):
        word = _clean_word(raw, language)
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        words.append((data["left"][i], data["top"][i], data["height"][i], word))
        lines.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(word)
        confs.append(conf)
    # Block mode (6) already groups skewed lines well; sparse mode (11) returns loose words.
    text_lines = [" ".join(ws) for ws in lines.values()] if psm == 6 else _group_rows(words)
    chars = sum(len(w[3]) for w in words)
    quality = (sum(confs) / len(confs)) * min(1.0, chars / 4) if confs else 0.0
    return text_lines, quality


def extract_text_from_image(data: bytes, language: str) -> list[str]:
    """Return the lines of `language` text found in the image (best reading first)."""
    configure_tesseract()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not read that image. Please upload a JPG or PNG photo.")

    best_lines, best_q = [], 0.0
    try:
        for variant in _variants(img):
            for psm in (6, 11):  # 6 = block of text, 11 = sparse text (signboards)
                lines, q = _read(variant, language, psm)
                if q > best_q:
                    best_lines, best_q = lines, q
            if best_q >= 85:
                break
    except pytesseract.TesseractError as exc:
        if "Failed loading language" in str(exc):
            raise OCRUnavailable(f"{language} text recognition isn't installed on the server.") from exc
        raise
    return best_lines if best_q >= MIN_QUALITY else []

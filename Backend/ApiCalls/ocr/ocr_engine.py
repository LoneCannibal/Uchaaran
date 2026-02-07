# Backend/ApiCalls/ocr/ocr_engine.py

from .preprocessors import *
import easyocr
import cv2
import numpy as np

EASY_OCR_CODES = {...}

PREPROCESS_MAP = {
    "Hindi": preprocess_devanagari,
    "Marathi": preprocess_devanagari,
    "Tamil": preprocess_tamil,
    "Malayalam": preprocess_malayalam,
    "Kannada": preprocess_kannada,
    "Telugu": preprocess_telugu,
    "Bengali": preprocess_bengali,
    "Odia": preprocess_odia,
    "Punjabi": preprocess_punjabi,
    "Gujarati": preprocess_gujarati
}

def ocr_extract_text(image_file, language):
    img_bytes = image_file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    image_file.seek(0)

    if img is None:
        return ""

    processor = PREPROCESS_MAP.get(language)
    processed = processor(img)

    reader = easyocr.Reader([EASY_OCR_CODES[language]], gpu=False)
    result = reader.readtext(processed, detail=0)

    if not result:
        return ""

    return " ".join(result).strip()

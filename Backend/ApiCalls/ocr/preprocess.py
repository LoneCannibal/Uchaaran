import cv2
import numpy as np


# ==========================================
# 1. Tamil — needs sharpening & Otsu threshold
# ==========================================
def preprocess_tamil(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    sharp = cv2.addWeighted(gray, 2.5, blur, -1.5, 0)
    _, bw = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


# ==========================================
# 2. Malayalam — smooth + threshold + dilation (VERY important)
# ==========================================
def preprocess_malayalam(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 3)
    _, bw = cv2.threshold(blur, 150, 255, cv2.THRESH_BINARY_INV)
    kernel = np.ones((2, 2), np.uint8)
    thick = cv2.dilate(bw, kernel, iterations=1)
    return thick


# ==========================================
# 3. Kannada — morphological open
# ==========================================
def preprocess_kannada(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    opened = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
    return opened


# ==========================================
# 4. Telugu — adaptive + dilation
# ==========================================
def preprocess_telugu(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    adapt = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 31, 10
    )
    kern = np.ones((2, 2), np.uint8)
    dil = cv2.dilate(adapt, kern, iterations=1)
    return dil


# ==========================================
# 5. Bengali — bilateral filter + Otsu
# ==========================================
def preprocess_bengali(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.bilateralFilter(gray, 5, 50, 50)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


# ==========================================
# 6. Odia — smooth + fixed threshold
# ==========================================
def preprocess_odia(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 5)
    _, bw = cv2.threshold(blur, 120, 255, cv2.THRESH_BINARY_INV)
    return bw


# ==========================================
# 7. Gujarati — simple Otsu threshold
# ==========================================
def preprocess_gujarati(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


# ==========================================
# 8. Punjabi (Gurmukhi) — high threshold
# ==========================================
def preprocess_punjabi(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    return bw


# ==========================================
# 9. Hindi / Marathi (Devanagari) — remove shirorekha
# ==========================================
def preprocess_devanagari(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Remove top line (shirorekha)
    kernel = np.ones((1, 50), np.uint8)
    removed = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)

    return removed


# ==========================================
# 10. Fallback — simple grayscale threshold
# ==========================================
def preprocess_generic(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw

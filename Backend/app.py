from flask import Flask, render_template, request, redirect, send_from_directory
import re
import requests
import os
import pathlib
import tempfile
import base64

from rapidfuzz import fuzz
from sarvamai import SarvamAI
from sarvamai.play import save

from Backend.ApiCalls.helpers.text_to_speech import tts
from Backend.ApiCalls.helpers.phonetic_help import phonetic_help

import pytesseract
import cv2



# --------------------------------------------------
# PATHS
# --------------------------------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

TEMPLATES_DIR = PROJECT_ROOT / "Frontend" / "Templates"
STATIC_DIR = PROJECT_ROOT / "Frontend" / "Static"

AUDIO_OUTPUT_DIR = pathlib.Path("/tmp/correct_pronunciation_output")

# --------------------------------------------------
# FLASK APP
# --------------------------------------------------
app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR)
)

app.config["ENV"] = "production"
app.config["DEBUG"] = False

# --------------------------------------------------
# ENV + SARVAM CLIENT
# --------------------------------------------------
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
if not SARVAM_API_KEY:
    raise RuntimeError("SARVAM_API_KEY not set")

client = SarvamAI(api_subscription_key=SARVAM_API_KEY)

# --------------------------------------------------
# LANGUAGE MAPS
# --------------------------------------------------
GOOGLE_LANG_MAP = {
    "Hindi": "hi",
    "Bengali": "bn",
    "Tamil": "ta",
    "Telugu": "te",
    "Gujarati": "gu",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Marathi": "mr",
    "Punjabi": "pa",
    "Odia": "or"
}

SARVAM_LANG_MAP = {
    "Hindi": "hi-IN",
    "Bengali": "bn-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
    "Gujarati": "gu-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Marathi": "mr-IN",
    "Punjabi": "pa-IN",
    "Odia": "or-IN",
    "English": "en-IN"
}

WORD_LANGUAGE_MAP = {
    "vizhinjam": "Malayalam",
    "kozhikode": "Malayalam",
    "pazham": "Tamil",
    "sutrchulal": "Tamil",
    "namaste": "Hindi",
    "dharti": "Hindi",
    "bhishon": "Bengali",
    "dhrubo": "Bengali",
    "draaksha": "Telugu",
    "sampurnam": "Telugu",
    "snehaankita": "Gujarati",
    "kshatriya": "Gujarati",
    "hrudaya": "Kannada",
    "dhwani": "Kannada",
    "chhadna": "Punjabi",
    "bhalla": "Punjabi",
    "dhrushti": "Odia",
    "chhabi": "Odia"
}

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def is_english(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z\s]+", text))


def transliterate_to_native(text: str, language: str) -> str:
    lang_code = GOOGLE_LANG_MAP.get(language)
    if not lang_code or not is_english(text):
        return text

    try:
        response = requests.get(
            "https://inputtools.google.com/request",
            params={
                "text": text,
                "itc": f"{lang_code}-t-i0-und",
                "num": 1
            },
            timeout=5
        ).json()

        if response[0] == "SUCCESS":
            return response[1][0][1][0]
    except Exception as e:
        print("Transliteration error:", e)

    return text


def clean_and_format(text: str) -> str:
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def save_base64_audio(data_url: str) -> str:
    header, encoded = data_url.split(",", 1)
    audio_bytes = base64.b64decode(encoded)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.write(audio_bytes)
    tmp.close()

    return tmp.name


def transcribe_audio(audio_path: str, language: str) -> str:
    """
    ✅ CORRECT Sarvam Speech-to-Text usage
    """
    lang_code = SARVAM_LANG_MAP.get(language, "en-IN")

    response = client.speech_to_text.transcribe(
        audio_path=audio_path,
        language_code=lang_code
    )

    if isinstance(response, dict):
        text = response.get("text", "")
    else:
        text = getattr(response, "text", "")

    return text.strip().lower()


def score_pronunciation(expected: str, spoken: str) -> float:
    similarity = fuzz.ratio(expected, spoken)
    return round((similarity / 100) * 10, 1)


def extract_text_from_image(image_path: str) -> str:
    """
    English OCR using Tesseract (no torch)
    """
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    text = pytesseract.image_to_string(
        gray,
        lang="eng",
        config="--psm 6"
    )

    return text.strip()


# --------------------------------------------------
# CORE PROCESSING
# --------------------------------------------------
def process_learn(language: str, text_input: str) -> dict:
    AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    safe_text = re.sub(r"[^\w\-]", "_", text_input.strip())
    filename = f"{safe_text}_{language}.wav"
    file_path = AUDIO_OUTPUT_DIR / filename

    how_to_say = phonetic_help(client, text_input)
    how_to_say = clean_and_format(how_to_say)

    if not file_path.exists():
        pronunciation_audio = tts(
            client,
            text=text_input,
            lang_code=GOOGLE_LANG_MAP[language] + "-IN"
        )
        save(pronunciation_audio, str(file_path))

    return {
        "language": language,
        "text": text_input,
        "pronunciation_audio": filename,
        "how_to_say": how_to_say
    }

# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@app.route("/")
def home():
    return render_template("Home.html")


@app.route("/learn/<word>")
def learn_prefilled(word):
    language = WORD_LANGUAGE_MAP.get(word.lower())
    if not language:
        return redirect("/learn")

    return render_template(
        "Learn.html",
        result=None,
        error=None,
        user_text=word,
        selected_language=language
    )


@app.route("/learn", methods=["GET", "POST"])
def learn():
    result = None
    error = None
    user_text = ""
    selected_language = ""

    if request.method == "POST":
        selected_language = request.form.get("language")

        typed_text = request.form.get("text_input", "").strip()
        image = request.files.get("image")

        if not selected_language:
            error = "Please select a language."

        # CASE 1: IMAGE PROVIDED → OCR
        elif image and image.filename:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            image.save(tmp.name)

            ocr_text = extract_text_from_image(tmp.name)

            if not ocr_text:
                error = "No readable text found in image."
            else:
                user_text = ocr_text

                processed_text = (
                    transliterate_to_native(ocr_text, selected_language)
                    if is_english(ocr_text)
                    else ocr_text
                )

                result = process_learn(selected_language, processed_text)

        # CASE 2: TYPED TEXT
        elif typed_text:
            user_text = typed_text

            processed_text = (
                transliterate_to_native(typed_text, selected_language)
                if is_english(typed_text)
                else typed_text
            )

            result = process_learn(selected_language, processed_text)

        else:
            error = "Please enter text or upload an image."

    return render_template(
        "Learn.html",
        result=result,
        error=error,
        user_text=user_text,
        selected_language=selected_language
    )



# @app.route("/learn", methods=["GET", "POST"])
# def learn():
#     result = None
#     error = None
#     user_text = ""
#     selected_language = ""

#     if request.method == "POST":
#         selected_language = request.form.get("language")
#         user_text = request.form.get("text_input", "").strip()

#         if not selected_language:
#             error = "Please select a language."
#         elif not user_text:
#             error = "Please provide text."
#         else:
#             processed_text = (
#                 transliterate_to_native(user_text, selected_language)
#                 if is_english(user_text)
#                 else user_text
#             )
#             result = process_learn(selected_language, processed_text)

#     return render_template(
#         "Learn.html",
#         result=result,
#         error=error,
#         user_text=user_text,
#         selected_language=selected_language
#     )

# --------------------------------------------------
# CHECK PRONUNCIATION
# --------------------------------------------------
@app.route("/check", methods=["GET", "POST"])
def check():
    result = None

    if request.method == "POST":
        language = request.form.get("language")
        expected_text = request.form.get("expected_text", "").strip().lower()

        audio_file = request.files.get("audio")
        mic_audio = request.form.get("mic_audio")

        audio_path = None

        if audio_file and audio_file.filename:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            audio_file.save(tmp.name)
            audio_path = tmp.name

        elif mic_audio:
            audio_path = save_base64_audio(mic_audio)

        else:
            return render_template("Check.html", result={"error": "No audio provided"})

        spoken_text = transcribe_audio(audio_path, language)

        if not spoken_text:
            return render_template("Check.html", result={"error": "Could not understand audio"})

        score = score_pronunciation(expected_text, spoken_text)

        result = {
            "expected": expected_text,
            "spoken": spoken_text,
            "score": score
        }

    return render_template("Check.html", result=result)


@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_OUTPUT_DIR, filename)


@app.route("/about")
def about():
    return render_template("About.html")

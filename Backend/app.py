from flask import Flask, render_template, request, redirect, send_from_directory, abort
import re
import requests
import os
import pathlib
import tempfile
import base64
import hashlib
import logging
import unicodedata

from rapidfuzz import fuzz
from sarvamai import SarvamAI
from sarvamai.play import save
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

from Backend.ApiCalls.helpers.text_to_speech import tts
from Backend.ApiCalls.helpers.phonetic_help import phonetic_help
from Backend.ApiCalls.helpers.speech_to_text import stt
from Backend.ApiCalls.ocr.ocr_engine import extract_text_from_image, configure_tesseract, OCRUnavailable  # noqa: F401

log = logging.getLogger("uchaaran")

# --------------------------------------------------
# PATHS
# --------------------------------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

TEMPLATES_DIR = PROJECT_ROOT / "Frontend" / "Templates"
STATIC_DIR = PROJECT_ROOT / "Frontend" / "Static"

# Cache of generated pronunciations. Override with UCHAARAN_AUDIO_DIR to keep it
# somewhere persistent; the default temp folder works on Windows and Linux.
AUDIO_OUTPUT_DIR = pathlib.Path(
    os.getenv("UCHAARAN_AUDIO_DIR", pathlib.Path(tempfile.gettempdir()) / "correct_pronunciation_output")
)

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
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # photos and voice clips

MAX_TEXT_CHARS = 60

# --------------------------------------------------
# ENV + SARVAM CLIENT
# --------------------------------------------------
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
if not SARVAM_API_KEY:
    raise RuntimeError("SARVAM_API_KEY not set")

client = SarvamAI(api_subscription_key=SARVAM_API_KEY, timeout=45)

# --------------------------------------------------
# LANGUAGES (single source of truth, also used by the templates)
# --------------------------------------------------
#             name         Google  Sarvam   script for scoring     Unicode block
LANGUAGES = {
    "Hindi":     ("hi", "hi-IN", sanscript.DEVANAGARI, (0x0900, 0x097F)),
    "Bengali":   ("bn", "bn-IN", sanscript.BENGALI,    (0x0980, 0x09FF)),
    "Tamil":     ("ta", "ta-IN", sanscript.TAMIL,      (0x0B80, 0x0BFF)),
    "Telugu":    ("te", "te-IN", sanscript.TELUGU,     (0x0C00, 0x0C7F)),
    "Gujarati":  ("gu", "gu-IN", sanscript.GUJARATI,   (0x0A80, 0x0AFF)),
    "Kannada":   ("kn", "kn-IN", sanscript.KANNADA,    (0x0C80, 0x0CFF)),
    "Malayalam": ("ml", "ml-IN", sanscript.MALAYALAM,  (0x0D00, 0x0D7F)),
    "Marathi":   ("mr", "mr-IN", sanscript.DEVANAGARI, (0x0900, 0x097F)),
    "Punjabi":   ("pa", "pa-IN", sanscript.GURMUKHI,   (0x0A00, 0x0A7F)),
    "Odia":      ("or", "od-IN", sanscript.ORIYA,      (0x0B00, 0x0B7F)),  # Sarvam uses od-IN, Google uses or
}
LANGUAGE_NAMES = list(LANGUAGES)

GOOGLE_LANG_MAP = {name: v[0] for name, v in LANGUAGES.items()}
SARVAM_LANG_MAP = {name: v[1] for name, v in LANGUAGES.items()}

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

# Bump when the TTS voice/model changes so old cached audio isn't reused.
TTS_VOICE = "bulbul:v2-default"


class UserError(Exception):
    """A problem the user can fix; shown on the page as-is."""


# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def is_english(text: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z\s'.\-]+", text)) and any(c.isalpha() for c in text)


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
        log.warning("Transliteration error: %s", e)

    return text


def script_language(text: str) -> str | None:
    """Name of the (first) language whose script most of `text` is written in."""
    counts: dict[str, int] = {}
    for ch in text:
        for name, (*_, (lo, hi)) in LANGUAGES.items():
            if lo <= ord(ch) <= hi:
                counts[name] = counts.get(name, 0) + 1
                break
    return max(counts, key=counts.get) if counts else None


def to_native_text(text: str, language: str) -> str:
    """Typed or scanned input -> NFC native-script text in `language`, or UserError."""
    text = " ".join((text or "").split())
    if not text:
        raise UserError("Please enter text or upload an image.")
    if len(text) > MAX_TEXT_CHARS:
        raise UserError(f"Please keep it short: up to {MAX_TEXT_CHARS} characters (a word or a name).")

    if is_english(text):
        text = transliterate_to_native(text, language)
        if is_english(text):
            raise UserError("Couldn't convert that to " + language + " script right now. "
                            "Please try again, or type the word in " + language + " script.")

    lo, hi = LANGUAGES[language][3]
    if not any(lo <= ord(ch) <= hi for ch in text):
        found = script_language(text)
        if found and LANGUAGES[found][3] != LANGUAGES[language][3]:
            raise UserError(f"That text is written in {found} script. Choose {found} as the language, "
                            f"or type the word in English letters.")
        raise UserError(f"Please type the word in {language} script or in English letters.")
    return unicodedata.normalize("NFC", text)


def clean_and_format(text: str) -> str:
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    """'data:audio/webm;codecs=opus;base64,....' -> (bytes, 'audio/webm')."""
    try:
        header, encoded = data_url.split(",", 1)
        mime = header[5:].split(";")[0] or "audio/webm"
        return base64.b64decode(encoded), mime
    except Exception:
        raise UserError("The recording was incomplete. Please record again.")


AUDIO_EXTENSIONS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav",
                    "audio/wave": "wav", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/x-m4a": "m4a",
                    "audio/aac": "aac", "audio/flac": "flac"}


def transcribe_audio(audio: bytes, mime: str, language: str) -> str:
    mime = (mime or "audio/wav").split(";")[0].lower()
    ext = AUDIO_EXTENSIONS.get(mime, "wav")
    return stt(client, audio, SARVAM_LANG_MAP[language], filename=f"recording.{ext}", content_type=mime)


def to_roman(text: str, language: str) -> str:
    """Romanise native text (ISO 15919) so pronunciations are compared as sounds,
    and the same scheme is applied to both sides."""
    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if ch.isalnum() or unicodedata.category(ch) in ("Mn", "Mc") or ch.isspace())
    return " ".join(transliterate(text, LANGUAGES[language][2], sanscript.ISO).lower().split())


def score_pronunciation(expected: str, spoken: str, language: str) -> float:
    similarity = fuzz.ratio(to_roman(expected, language), to_roman(spoken, language))
    return round((similarity / 100) * 10, 1)


# --------------------------------------------------
# CORE PROCESSING
# --------------------------------------------------
def cache_key(language: str, text: str) -> str:
    # Hash the exact text: sanitising Unicode into a filename made different words
    # collide (पाल and पील both became प_ल_Hindi.wav).
    key = f"{TTS_VOICE}|{SARVAM_LANG_MAP[language]}|{unicodedata.normalize('NFC', text)}"
    return f"{GOOGLE_LANG_MAP[language]}_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:20]}"


def _atomic_write(path: pathlib.Path, write) -> None:
    tmp = path.with_name(path.name + ".part")
    write(str(tmp))
    os.replace(tmp, path)  # readers never see a half-written file


def process_learn(language: str, text_input: str) -> dict:
    AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    key = cache_key(language, text_input)
    filename = f"{key}.wav"
    file_path = AUDIO_OUTPUT_DIR / filename
    guide_path = AUDIO_OUTPUT_DIR / f"{key}.txt"

    if not file_path.exists():
        try:
            pronunciation_audio = tts(client, text=text_input, lang_code=SARVAM_LANG_MAP[language])
            _atomic_write(file_path, lambda p: save(pronunciation_audio, p))
        except Exception:
            log.exception("TTS failed for %s", language)
            raise UserError("Couldn't generate the pronunciation right now. Please try again in a moment.")

    # The guide is helpful but not essential: cache it, and never fail the request over it.
    how_to_say = None
    if guide_path.exists():
        how_to_say = guide_path.read_text(encoding="utf-8")
    else:
        try:
            how_to_say = clean_and_format(phonetic_help(client, text_input, language))
            _atomic_write(guide_path, lambda p: pathlib.Path(p).write_text(how_to_say, encoding="utf-8"))
        except Exception:
            log.exception("Phonetic help failed")

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
        languages=LANGUAGE_NAMES,
        result=None,
        error=None,
        user_text=word,
        selected_language=language
    )


@app.route("/learn", methods=["GET", "POST"])
def learn():
    result = None
    error = None
    user_text = request.args.get("word", "")
    selected_language = request.args.get("language", "")

    if request.method == "POST":
        selected_language = request.form.get("language", "")
        typed_text = request.form.get("text_input", "").strip()
        user_text = typed_text
        # Camera and gallery are two inputs with the same name; use whichever was filled.
        image = next((f for f in request.files.getlist("image") if f and f.filename), None)

        try:
            if selected_language not in LANGUAGES:
                raise UserError("Please select a language.")

            ocr_lines = []
            # CASE 1: IMAGE PROVIDED -> OCR
            if image:
                ocr_lines = extract_text_from_image(image.read(), selected_language)
                if not ocr_lines:
                    raise UserError(f"No {selected_language} text found in the image. Try a closer, "
                                    f"well-lit photo, and check the language is right.")
                user_text = ocr_lines[0]

            # CASE 2: TYPED TEXT (or the first line read from the photo)
            processed_text = to_native_text(user_text, selected_language)
            result = process_learn(selected_language, processed_text)
            result["ocr_lines"] = ocr_lines
        except UserError as e:
            error = str(e)
        except OCRUnavailable as e:
            error = f"{e} Please type the word instead."
        except ValueError as e:
            error = str(e)

    return render_template(
        "Learn.html",
        languages=LANGUAGE_NAMES,
        result=result,
        error=error,
        user_text=user_text,
        selected_language=selected_language,
        auto=request.args.get("auto") == "1",
    )


# --------------------------------------------------
# CHECK PRONUNCIATION
# --------------------------------------------------
@app.route("/check", methods=["GET", "POST"])
def check():
    result = None
    word = request.args.get("word", "")
    language = request.args.get("language", "")

    if request.method == "POST":
        language = request.form.get("language", "")
        word = request.form.get("expected_text", "").strip()

        audio_file = request.files.get("audio")
        mic_audio = request.form.get("mic_audio")

        try:
            if language not in LANGUAGES:
                raise UserError("Please select a language.")
            expected_text = to_native_text(word, language)

            if audio_file and audio_file.filename:
                audio, mime = audio_file.read(), audio_file.mimetype
            elif mic_audio:
                audio, mime = decode_data_url(mic_audio)
            else:
                raise UserError("Please record your voice or upload an audio file.")

            try:
                spoken_text = transcribe_audio(audio, mime, language)
            except Exception:
                log.exception("Speech-to-text failed")
                raise UserError("Couldn't process the recording right now. Please try again in a moment.")

            if not spoken_text:
                raise UserError("Could not understand the audio. Speak clearly and a little louder, then try again.")

            score = score_pronunciation(expected_text, spoken_text, language)
            result = {
                "expected": expected_text,
                "spoken": spoken_text,
                "score": score
            }
        except UserError as e:
            result = {"error": str(e)}

    return render_template("Check.html", languages=LANGUAGE_NAMES, result=result,
                           word=word, selected_language=language)


@app.route("/audio/<filename>")
def serve_audio(filename):
    if not re.fullmatch(r"[a-z]{2}_[0-9a-f]{20}\.wav", filename):
        abort(404)
    return send_from_directory(AUDIO_OUTPUT_DIR, filename, mimetype="audio/wav")


@app.route("/about")
def about():
    return render_template("About.html")


@app.errorhandler(413)
def too_large(_e):
    return render_template("Learn.html", languages=LANGUAGE_NAMES, result=None,
                           error="That file is too large (max 10 MB). Please use a smaller photo.",
                           user_text="", selected_language=""), 413


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(port=int(os.getenv("PORT", "5000")))

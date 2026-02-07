from flask import Flask, render_template, request, redirect
import re
import requests
from sarvamai import SarvamAI
from sarvamai.play import save
import os, pathlib
from ApiCalls.helpers.text_to_speech import tts
from ApiCalls.helpers.phonetic_help import phonetic_help
from flask import send_from_directory

# --------------------------------------------------
# GLOBALS
# --------------------------------------------------
client = None
BASE_DIR = pathlib.Path(__file__).resolve().parent
AUDIO_OUTPUT_DIR = BASE_DIR.parent / "Data" / "correct_pronunciation_output"

app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static"
)

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
def is_english(text):
    return bool(re.fullmatch(r"[A-Za-z\s]+", text))


def transliterate_to_native(text, language):
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


def clean_and_format(text):
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------
# CORE PROCESSING
# --------------------------------------------------
def process_learn(language, text_input):
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


@app.route("/learn/<word>", methods=["GET"])
def learn_prefilled(word):
    language = WORD_LANGUAGE_MAP.get(word.lower())
    if not language:
        return redirect("/learn")

    return render_template(
        "learn.html",
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
        user_text = request.form.get("text_input", "").strip()

        if not selected_language:
            error = "Please select a language."
        elif not user_text:
            error = "Please provide text."
        else:
            processed_text = (
                transliterate_to_native(user_text, selected_language)
                if is_english(user_text)
                else user_text
            )
            result = process_learn(selected_language, processed_text)

    return render_template(
        "learn.html",
        result=result,
        error=error,
        user_text=user_text,
        selected_language=selected_language
    )

@app.route("/check")
def check():
    return render_template("Check.html")


@app.route("/audio/<filename>")
def serve_audio(filename):
    return send_from_directory(AUDIO_OUTPUT_DIR, filename)


@app.route("/about")
def about():
    return render_template("About.html")


# --------------------------------------------------
# RUN
# --------------------------------------------------
if __name__ == "__main__":
    SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
    if not SARVAM_API_KEY:
        raise KeyError("SARVAM_API_KEY not found")

    client = SarvamAI(api_subscription_key=SARVAM_API_KEY)
    #app.run(debug=False)

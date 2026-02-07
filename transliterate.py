# Import the necessary modules from indic_transliteration
from indic_transliteration import sanscript
from indic_transliteration.sanscript import SchemeMap, SCHEMES, transliterate

# Input data for transliteration
data = 'idam adbhutam'

# Transliterate from Harvard-Kyoto (HK) to Telugu
print(transliterate(data, sanscript.HK, sanscript.TELUGU)) 




from flask import Flask, render_template, request
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
import re

app = Flask(__name__,
            template_folder="../frontend/templates",
            static_folder="../frontend/static"
            )

# ----------------------
# Language Configuration
# ----------------------
LANG_MAP = {
    "Hindi": sanscript.DEVANAGARI,
    "Bengali": sanscript.BENGALI,
    "Tamil": sanscript.TAMIL,
    "Telugu": sanscript.TELUGU,
    "Gujarati": sanscript.GUJARATI,
    "Kannada": sanscript.KANNADA,
    "Malayalam": sanscript.MALAYALAM,
    "Marathi": sanscript.DEVANAGARI,
    "Punjabi": sanscript.GURMUKHI,
    "Odia": sanscript.ORIYA
}

def is_english(text):
    return bool(re.fullmatch(r"[A-Za-z\s]+", text))

def transliterate_to_native(text, language):
    script = LANG_MAP.get(language)
    if not script:
        return text

    # Already native script?
    if any('\u0900' <= ch <= '\u0FFF' for ch in text):
        return text

    # Convert English -> phonetic -> Indian script
    return transliterate(text, sanscript.ITRANS, script)


# ----------------------
# ROUTES
# ----------------------

@app.route("/")
def home():
    return render_template("Home.html")


@app.route("/learn", methods=["GET", "POST"])
def learn():
    result = None
    error = None

    if request.method == "POST":
        language = request.form.get("language")
        text_input = request.form.get("text_input")
        image = request.files.get("image")

        # (1) Language required
        if not language:
            error = "Please select a language."

        # (2) Either text or image required
        elif not text_input and not image:
            error = "Please provide text or upload an image."

        else:
            # Convert English -> native if needed
            if text_input and is_english(text_input):
                text_input = transliterate_to_native(text_input, language)

            # Pass to your backend logic
            result = process_learn(language, text_input, image)

    return render_template("learn.html", result=result, error=error)



@app.route("/check", methods=["GET", "POST"])
def check():
    result = None
    if request.method == "POST":
        language = request.form.get("language")
        audio_file = request.files.get("audio")
        result = process_pronunciation(language, audio_file)
    return render_template("check.html", result=result)


@app.route("/history")
def history():
    return render_template("History.html")


if __name__ == "__main__":
    app.run(debug=True)

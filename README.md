# उचारान् (Uchaaran)

Learn how to pronounce words in Indian languages. Type a word, in English letters or its own script, or snap a photo of a signboard, and hear the native pronunciation with a syllable-by-syllable guide. Then record yourself and check how close you were.

Supported: Hindi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Marathi, Punjabi, Odia.

---

## 📐 Interview & Architecture Deep-Dive

The design reasoning (technology choices and rejected alternatives, data model, failure modes, and a path to 100× scale) is in a local guide, `INTERVIEW_PREP.md`. It is git-ignored, along with every Markdown file except this README, so it isn't on GitHub. Ask a team member for a copy.

---

## Architecture

```
Browser (Jinja + Bootstrap)
   │
   ▼
Flask (Backend/app.py)
   ├─ /learn  : photo ─► Tesseract OCR (Indian-script models) ─► text
   │            text  ─► Google Input Tools (English → native script) ─► script check
   │                  ─► Sarvam TTS (cached .wav) + Sarvam chat "how to say it" (cached)
   ├─ /check  : recording/upload ─► Sarvam speech-to-text ─► both sides romanised (ISO 15919)
   │                              ─► similarity score /10
   └─ /audio/<file> : serves cached pronunciation audio
```

| Layer | Technology |
|---|---|
| Backend | Python, Flask, gunicorn |
| Frontend | Jinja templates, Bootstrap 5 |
| Speech & LLM | [Sarvam AI](https://www.sarvam.ai/): text-to-speech (`bulbul:v2`), speech-to-text (`saarika:v2.5`), chat |
| Transliteration | Google Input Tools |
| OCR | Tesseract + OpenCV, with `tessdata_best` models for all 10 scripts |
| Scoring | `indic_transliteration` (ISO 15919) + `rapidfuzz` |

## Requirements

- **Python 3.11+**
- A **Sarvam AI API key**
- **Tesseract OCR**, for the photo feature:
  - Windows: `winget install UB-Mannheim.TesseractOCR`
  - Linux: `apt install tesseract-ocr`
  - macOS: `brew install tesseract`

## Quick start

Run these from the **project root**.

```powershell
python -m venv .venv
.venv\Scripts\activate                     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/download_tessdata.py        # Indian-language OCR models → ./tessdata (~120 MB, once)

$env:SARVAM_API_KEY = "<your key>"         # bash: export SARVAM_API_KEY="<your key>"
python -m Backend.app                      # http://127.0.0.1:5000
```

The app refuses to start without `SARVAM_API_KEY`. Never put the key in code; use the environment variable or a git-ignored `.env`.

### Optional settings

| Variable | Default | Purpose |
|---|---|---|
| `UCHAARAN_AUDIO_DIR` | `<system temp>/correct_pronunciation_output` | Where generated audio and guides are cached |
| `TESSERACT_CMD` | auto-detected | Path to `tesseract` if it isn't on `PATH` |
| `TESSDATA_PREFIX` | `./tessdata` if present | Where Tesseract's language models live |
| `PORT` | `5000` | Port for `python -m Backend.app` |

## Tests

```powershell
pip install -r requirements-dev.txt
pytest -q
```

- The tests use the **real Sarvam SDK** with a mock HTTP transport, so no API key or credits are needed.
- They cover Learn, Check, the cache, the error paths, the upload limits and real OCR. The OCR test is skipped if Tesseract or `./tessdata` is missing.

## Deploying (Heroku-style)

- **`Procfile`:** `web: gunicorn --threads 8 --timeout 120 Backend.app:app`
- **OCR:** add the `heroku-community/apt` buildpack. The **`Aptfile`** installs Tesseract and the Indian-language packs. Then set `TESSDATA_PREFIX` to the installed `tessdata` folder (under `/app/.apt/usr/share/tesseract-ocr/`).
- **Config var:** set `SARVAM_API_KEY`.
- **Cache:** the audio cache lives on local disk, so it is per-dyno and resets on restart.

## Project structure

```
Backend/
  app.py                  Flask app: routes, languages, transliteration, caching, scoring
  ApiCalls/helpers/       Sarvam wrappers: text_to_speech, speech_to_text, phonetic_help
  ApiCalls/ocr/           Tesseract OCR engine (preprocessing variants + script cleanup)
Frontend/
  Templates/              Home, Learn, Check, About pages
  Static/                 CSS, logo, team images
scripts/download_tessdata.py   Downloads the OCR language models
tests/                    pytest suite (+ fixtures/malayalam_sign.png)
Data/                     Sample audio from early testing
Docs/                     Project write-up (उचारान्.pdf)
```

## Known limitations

- **OCR** reads clear printed text well. Stylised signboards and some Bengali or Telugu conjuncts are weaker, so the recognised text is shown in the box for the user to correct.
- **Scoring** compares the speech-to-text transcript with the expected word (as sounds, via ISO 15919 romanisation). It reflects what the speech model *heard*, not a phoneme-level acoustic analysis.
- **Old key:** an old Sarvam API key exists in git history. Revoke it in the Sarvam dashboard if that hasn't been done.

## Team

Aakash SD · Bhagavath M S, Team MSD

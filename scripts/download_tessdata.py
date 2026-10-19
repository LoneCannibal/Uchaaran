"""
Download Tesseract's Indian-language models into ./tessdata (about 120 MB).

    python scripts/download_tessdata.py

Tesseract installs with English only, which can't read Indian scripts. The app
uses ./tessdata automatically when it exists. On Linux servers you can instead
install the system packages listed in the Aptfile.
"""
import pathlib
import urllib.request

TARGET = pathlib.Path(__file__).resolve().parent.parent / "tessdata"
URL = "https://github.com/tesseract-ocr/tessdata_best/raw/main/{}.traineddata"
LANGS = ["eng", "osd", "hin", "ben", "tam", "tel", "guj", "kan", "mal", "mar", "pan", "ori"]

if __name__ == "__main__":
    TARGET.mkdir(exist_ok=True)
    for lang in LANGS:
        path = TARGET / f"{lang}.traineddata"
        if path.exists():
            print(f"  {lang}: already there")
            continue
        print(f"  {lang}: downloading…")
        urllib.request.urlretrieve(URL.format(lang), path)
    print(f"Done: {TARGET}")

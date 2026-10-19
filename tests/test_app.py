"""
End-to-end tests for the Flask app.

The real Sarvam SDK is used, but its HTTP traffic goes to a mock transport, so
requests are built and validated exactly as in production without an API key
or credits. Google Input Tools is faked too, so the suite runs offline.

    pip install -r requirements-dev.txt
    pytest -q
"""
import base64
import io
import json
import os
import shutil
import wave

import httpx
import pytest

os.environ.setdefault("SARVAM_API_KEY", "test-key")

import Backend.app as app_module  # noqa: E402
from sarvamai import SarvamAI  # noqa: E402

TRANSLITERATIONS = {
    "vizhinjam": "വിഴിഞ്ഞം",
    "namaste": "नमस्ते",
    "bhubaneswar": "ଭୁବନେଶ୍ୱର",
}


def _wav_bytes(seconds: float = 0.3, rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


class FakeSarvam:
    """Records every request the SDK sends and answers like the real API."""

    def __init__(self):
        self.calls: list[tuple[str, httpx.Request]] = []
        self.transcript = ""
        self.fail = set()  # endpoints that should return HTTP 500

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        kind = ("tts" if path.endswith("/text-to-speech") else
                "stt" if path.endswith("/speech-to-text") else
                "chat" if path.endswith("/chat/completions") else path)
        self.calls.append((kind, request))
        if kind in self.fail:
            return httpx.Response(500, json={"error": {"message": "boom"}})
        if kind == "tts":
            body = json.loads(request.content)
            assert body["target_language_code"] in {
                "bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN", "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN"
            }, f"invalid TTS language code {body['target_language_code']}"
            return httpx.Response(200, json={"request_id": "r1", "audios": [base64.b64encode(_wav_bytes()).decode()]})
        if kind == "stt":
            return httpx.Response(200, json={"request_id": "r2", "transcript": self.transcript, "language_code": None})
        if kind == "chat":
            return httpx.Response(200, json={
                "id": "c1", "object": "chat.completion", "created": 0, "model": "sarvam-m",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "**Say it like:** vi-zhin-jam"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })
        return httpx.Response(404)

    def count(self, kind: str) -> int:
        return sum(1 for k, _ in self.calls if k == kind)

    def last(self, kind: str) -> httpx.Request:
        return [r for k, r in self.calls if k == kind][-1]


class FakeInputTools:
    def __init__(self, text):
        self.text = text

    def json(self):
        native = TRANSLITERATIONS.get(self.text.lower())
        return ["SUCCESS", [[self.text, [native]]]] if native else ["SUCCESS", [[self.text, [self.text]]]]


@pytest.fixture
def sarvam(monkeypatch, tmp_path):
    fake = FakeSarvam()
    client = SarvamAI(api_subscription_key="test-key", httpx_client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    monkeypatch.setattr(app_module, "client", client)
    monkeypatch.setattr(app_module, "AUDIO_OUTPUT_DIR", tmp_path / "audio")
    monkeypatch.setattr(app_module.requests, "get", lambda url, params=None, **kw: FakeInputTools(params["text"]))
    return fake


@pytest.fixture
def http(sarvam):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def page(resp) -> str:
    return resp.get_data(as_text=True)


# ---------------------------------------------------------------- pages
@pytest.mark.parametrize("path", ["/", "/learn", "/check", "/about"])
def test_pages_render(http, path):
    assert http.get(path).status_code == 200


def test_example_word_prefills_learn(http):
    import re
    html = page(http.get("/learn/vizhinjam"))
    assert ">vizhinjam</textarea>" in html
    assert re.search(r'value="Malayalam"\s+selected', html)


def test_audio_route_blocks_path_traversal(http):
    assert http.get("/audio/..%2Fapp.py").status_code == 404


# ---------------------------------------------------------------- learn
def test_learn_english_word_is_transliterated_and_spoken(http, sarvam):
    html = page(http.post("/learn", data={"language": "Malayalam", "text_input": "vizhinjam"}))
    assert "വിഴിഞ്ഞം" in html
    assert json.loads(sarvam.last("tts").content)["target_language_code"] == "ml-IN"
    assert json.loads(sarvam.last("tts").content)["text"] == "വിഴിഞ്ഞം"
    assert "vi-zhin-jam" in html
    src = html.split('src="/audio/')[1].split('"')[0]
    assert http.get(f"/audio/{src}").status_code == 200


def test_learn_odia_uses_sarvam_odia_code(http, sarvam):
    http.post("/learn", data={"language": "Odia", "text_input": "bhubaneswar"})
    assert json.loads(sarvam.last("tts").content)["target_language_code"] == "od-IN"


def test_learn_repeat_word_is_served_from_cache(http, sarvam):
    for _ in range(2):
        http.post("/learn", data={"language": "Hindi", "text_input": "namaste"})
    assert sarvam.count("tts") == 1
    assert sarvam.count("chat") == 1, "the 'how to say it' guide should be cached with the audio"


def test_learn_different_words_never_share_audio(http, sarvam):
    """पाल (paal) and पील (peel) differ only in the vowel sign."""
    a = page(http.post("/learn", data={"language": "Hindi", "text_input": "पाल"}))
    b = page(http.post("/learn", data={"language": "Hindi", "text_input": "पील"}))
    assert sarvam.count("tts") == 2
    src = lambda html: html.split('src="/audio/')[1].split('"')[0]  # noqa: E731
    assert src(a) != src(b)


def test_learn_rejects_text_in_another_script(http, sarvam):
    html = page(http.post("/learn", data={"language": "Hindi", "text_input": "வணக்கம்"}))
    assert "Tamil" in html
    assert sarvam.count("tts") == 0


def test_learn_survives_guide_failure(http, sarvam):
    sarvam.fail.add("chat")
    resp = http.post("/learn", data={"language": "Hindi", "text_input": "namaste"})
    assert resp.status_code == 200
    assert 'src="/audio/' in page(resp), "audio should still be returned when only the guide fails"


def test_learn_reports_tts_failure_cleanly(http, sarvam):
    sarvam.fail.add("tts")
    resp = http.post("/learn", data={"language": "Hindi", "text_input": "namaste"})
    assert resp.status_code == 200
    assert "try again" in page(resp).lower()


def test_learn_image_upload_reaches_ocr(http, sarvam, monkeypatch):
    monkeypatch.setattr(app_module, "extract_text_from_image",
                        lambda data, language: ["വിഴിഞ്ഞം"], raising=False)
    html = page(http.post("/learn", data={
        "language": "Malayalam", "text_input": "",
        "image": (io.BytesIO(b"fake-image"), "sign.jpg"),
    }, content_type="multipart/form-data"))
    assert "വിഴിഞ്ഞം" in html
    assert sarvam.count("tts") == 1


def test_learn_form_sends_image_field():
    with open(app_module.TEMPLATES_DIR / "Learn.html", encoding="utf-8") as f:
        html = f.read()
    assert 'name="image"' in html, "camera/gallery inputs must be named 'image' or the photo is never uploaded"


# ---------------------------------------------------------------- check
WEBM = "data:audio/webm;codecs=opus;base64," + base64.b64encode(b"\x1aE\xdf\xa3fake-webm").decode()


def test_check_scores_english_input_against_native_transcript(http, sarvam):
    sarvam.transcript = "नमस्ते"
    html = page(http.post("/check", data={"language": "Hindi", "expected_text": "namaste", "mic_audio": WEBM}))
    assert "10.0/10" in html
    stt = sarvam.last("stt")
    assert b'name="language_code"' in stt.content and b"hi-IN" in stt.content
    assert b"audio/webm" in stt.content, "browser recordings are webm and must be labelled as such"


def test_check_partial_match_scores_lower(http, sarvam):
    sarvam.transcript = "नमस्ती"
    html = page(http.post("/check", data={"language": "Hindi", "expected_text": "नमस्ते", "mic_audio": WEBM}))
    score = float(html.split("/10")[0].rsplit(">", 1)[1].strip())
    assert 5 <= score < 10


def test_check_accepts_uploaded_file(http, sarvam):
    sarvam.transcript = "നമസ്കാരം"
    resp = http.post("/check", data={
        "language": "Malayalam", "expected_text": "നമസ്കാരം",
        "audio": (io.BytesIO(_wav_bytes()), "me.wav", "audio/wav"),
    }, content_type="multipart/form-data")
    assert "10.0/10" in page(resp)


def test_check_without_audio_shows_error(http, sarvam):
    resp = http.post("/check", data={"language": "Hindi", "expected_text": "namaste"})
    assert resp.status_code == 200
    assert "record" in page(resp).lower() or "audio" in page(resp).lower()


def test_check_empty_transcript_shows_error(http, sarvam):
    sarvam.transcript = ""
    resp = http.post("/check", data={"language": "Hindi", "expected_text": "namaste", "mic_audio": WEBM})
    assert resp.status_code == 200
    assert "understand" in page(resp).lower()


def test_check_stt_failure_shows_error(http, sarvam):
    sarvam.fail.add("stt")
    resp = http.post("/check", data={"language": "Hindi", "expected_text": "namaste", "mic_audio": WEBM})
    assert resp.status_code == 200
    assert "try again" in page(resp).lower()


# ---------------------------------------------------------------- limits
def test_oversized_upload_is_rejected(http):
    big = io.BytesIO(b"0" * (11 * 1024 * 1024))
    resp = http.post("/learn", data={"language": "Hindi", "image": (big, "big.jpg")}, content_type="multipart/form-data")
    assert resp.status_code == 413


# ---------------------------------------------------------------- real OCR (needs Tesseract + Indian tessdata)
def _tesseract_ready():
    try:
        import pytesseract
        app_module.configure_tesseract()
        return {"mal", "hin"} <= set(pytesseract.get_languages(config=""))
    except Exception:
        return False


@pytest.mark.skipif(not shutil.which("tesseract") and not os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                    reason="Tesseract not installed")
def test_real_ocr_reads_malayalam_sign():
    if not _tesseract_ready():
        pytest.skip("Indian-language tessdata not installed (python scripts/download_tessdata.py)")
    sample = os.path.join(os.path.dirname(__file__), "fixtures", "malayalam_sign.png")
    with open(sample, "rb") as f:
        lines = app_module.extract_text_from_image(f.read(), "Malayalam")
    assert lines and lines[0] == "വിഴിഞ്ഞം"

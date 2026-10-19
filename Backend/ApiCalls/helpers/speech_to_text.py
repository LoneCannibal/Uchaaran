MODEL = "saarika:v2.5"


def stt(client, audio: bytes, lang_code: str, filename: str = "audio.wav", content_type: str = "audio/wav") -> str:
    """
    Transcribe a short clip with Sarvam speech-to-text.

    `audio` is the raw file bytes. The filename and content type tell Sarvam the
    format: browser recordings are usually webm/ogg, not wav.
    """
    response = client.speech_to_text.transcribe(
        file=(filename, audio, content_type),
        model=MODEL,
        language_code=lang_code,
    )
    return (response.transcript or "").strip()

from sarvamai import SarvamAI

MODEL = "saarika:v2.5"


def stt(client, filename, lang_code) -> str:
    client = SarvamAI(
        api_subscription_key="sk_rr5djtfm_pEwx0WELS8wWyhI386Ghdpka"
    )

    response = client.speech_to_text.transcribe(
        file=open(filename, "rb"),
        model= MODEL,
        language_code=lang_code
    )
    return (response.transcript)

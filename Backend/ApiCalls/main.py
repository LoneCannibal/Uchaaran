'''
Docstring for Backend.APICalls.main
Ideally this file should handle all the authentication for the sarvam api
'''
from sarvamai import SarvamAI
from sarvamai.play import play, save
import os
from helpers.speech_to_text import stt


if __name__ == "__main__":
    SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
    if not SARVAM_API_KEY:
        raise KeyError("SARVAM_API_KEY : API key not found. Please set it in enviroment variables")

    client = SarvamAI(
        api_subscription_key=SARVAM_API_KEY
    )
    transcription  = stt(client, "C:\\Users\\Aakash\\Documents\\DEHack\\output.wav", lang_code="ml-IN")
    print(transcription)


 
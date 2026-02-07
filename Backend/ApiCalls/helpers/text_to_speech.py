from sarvamai import SarvamAI
from sarvamai.play import play, save
import os


def tts(client, text, lang_code):

    response = client.text_to_speech.convert(
        text=text,
        target_language_code=lang_code,
        enable_preprocessing=True
    )

    # Play the audio
    #play(response)

    # Save the response to a file
    #save(response, "output.wav")
    return response




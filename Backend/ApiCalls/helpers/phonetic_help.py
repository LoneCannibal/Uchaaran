from sarvamai import SarvamAI


def phonetic_help(client, text)-> str:
    response = client.chat.completions(
        messages=[
            {"role": "system", "content": "The user requires help in pronuncing a word in a language that they might not know. First give the neophonetic pronunciation in English, then expalain how to pronunce each syllable."},
            {"role": "user", "content": "The word I'm trying to pronunce is: "+str(text)}
        ],
        temperature=0.5,
        top_p=1,
        max_tokens=1000,
    )

    print(response)
    return response.choices[0].message.content.strip()

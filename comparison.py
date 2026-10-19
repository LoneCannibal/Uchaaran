import os

from sarvamai import SarvamAI

client = SarvamAI(
    api_subscription_key=os.environ["SARVAM_API_KEY"],
)

response = client.chat.completions(
    messages=[
        {"role": "user", "content": "this is the proper way to say a word: വിഴിഞ്ഞം. This is how user said it: ബിസിംഗം. Compare both pronounciations in detail and give a score out of 10 based on how close the pronunciation is to the real pronunciation of the word. "}
    ],
    temperature=0.5,
    top_p=1,
    max_tokens=1000,
)

print(response)

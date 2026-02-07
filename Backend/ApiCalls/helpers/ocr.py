import requests

OCR_API_URL = "https://api.ocr.space/parse/image"

class OCRService:
    def __init__(self, api_key):
        self.api_key = api_key

    def extract_text(self, file_storage, language="eng"):
        """
        file_storage: Flask FileStorage object
        language: OCR language code (eng, hin, tam, tel, kan, mal, mar, ben, guj, pan, ori)
        """

        response = requests.post(
            OCR_API_URL,
            headers={"apikey": self.api_key},
            files={"file": (file_storage.filename, file_storage.stream, file_storage.mimetype)},
            data={
                "language": language,
                "OCREngine": 2,   # best engine
                "detectOrientation": True,
                "scale": True
            }
        )

        result = response.json()

        if result.get("IsErroredOnProcessing"):
            raise Exception(result.get("ErrorMessage"))

        parsed = result.get("ParsedResults")
        if not parsed:
            return ""

        return parsed[0].get("ParsedText", "").strip()

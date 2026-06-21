from deep_translator import GoogleTranslator

def translate_text(text, language="en"):

    if not text:
        return ""

    if language == "en":
        return text

    try:
        translated = GoogleTranslator(
            source="auto",
            target=language   # hi or te
        ).translate(text)

        return translated

    except Exception as e:
        print("Translation Error:", e)
        return text
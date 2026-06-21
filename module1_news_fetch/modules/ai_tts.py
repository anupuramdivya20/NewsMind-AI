from google.cloud import texttospeech
import os

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-account.json"

def generate_voice(text, language="en"):
    client = texttospeech.TextToSpeechClient()

    voice_map = {
        "en": ("en-IN", "en-IN-Wavenet-D"),
        "hi": ("hi-IN", "hi-IN-Wavenet-A"),
        "te": ("te-IN", "te-IN-Standard-A")
    }

    lang_code, voice_name = voice_map.get(language, voice_map["en"])

    synthesis_input = texttospeech.SynthesisInput(text=text)

    voice = texttospeech.VoiceSelectionParams(
        language_code=lang_code,
        name=voice_name
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    filename = "static/voice.mp3"

    with open(filename, "wb") as out:
        out.write(response.audio_content)

    return filename
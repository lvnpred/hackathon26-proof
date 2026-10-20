"""Groq hosted Whisper (cloud): same request shape as OpenAI, about a third of whisper-1's price."""
from doctor_dictation.providers.stt.openai import OpenAiCompatibleStt

URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class GroqStt(OpenAiCompatibleStt):
    name, label, engine, key_env, url = "groq", "Groq", "groq-whisper-api", "GROQ_API_KEY", URL

    def __init__(self, settings):
        super().__init__(settings.groq_api_key, settings.groq_stt_model)

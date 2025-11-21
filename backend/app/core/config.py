import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

class Settings(BaseModel):
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    PROJECT_NAME: str = "Anti-Hallucination Empathy Engine"

settings = Settings()

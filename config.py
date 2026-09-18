"""
GridWise Central Configuration

Manages environment variables and application settings.
"""

import os
from typing import Optional


from dotenv import load_dotenv

class Settings:
    """Centralized application settings."""
    
    def __init__(self):
        load_dotenv()
        # LLM Settings
        self.gemini_api_key: Optional[str] = os.getenv("GOOGLE_GEMINI_API_KEY")
        self.gemini_model: str = os.getenv("GOOGLE_GEMINI_MODEL", "gemini-3-flash")
        
        # Timeout Settings (in seconds)
        self.llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "10"))
        self.solver_timeout_seconds: int = int(os.getenv("SOLVER_TIMEOUT_SECONDS", "20"))
        
        # API Metadata
        self.pipeline_version: str = os.getenv("PIPELINE_VERSION", "1.0")
        
    def validate(self):
        """Validate critical settings."""
        if not self.gemini_api_key:
            raise ValueError("GOOGLE_GEMINI_API_KEY is missing or empty. Please set it in your environment.")


# Singleton instance
settings = Settings()

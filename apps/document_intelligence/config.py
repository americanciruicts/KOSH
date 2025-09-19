import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    
    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/docai"
    
    # File Upload Settings
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    allowed_extensions_str: str = "pdf,docx,xlsx,pptx,png,jpg,jpeg,html,eml,msg,zip,txt,csv"
    
    @property
    def allowed_extensions(self) -> List[str]:
        return self.allowed_extensions_str.split(",")
    
    # Directory Settings
    upload_dir: str = "uploads"
    output_dir: str = "outputs"
    log_dir: str = "logs"
    
    # Security
    secret_key: str = "your-secret-key-change-this"
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"

settings = Settings()
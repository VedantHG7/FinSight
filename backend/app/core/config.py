"""
FinSight Backend Core Configuration
"""
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import List, Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "FinSight API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
    ]

    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/finsight_db",
        env="DATABASE_URL"
    )
    
    COOKIE_SECURE: bool = False
    PUBLIC_APP_URL: str = 'http://127.0.0.1:5173'
    SMTP_HOST: str = ''
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ''
    SMTP_PASSWORD: str = ''
    SMTP_FROM_EMAIL: str = ''
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False

    # Security
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        env="SECRET_KEY"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Storage
    STORAGE_BACKEND: str = Field(default="local", env="STORAGE_BACKEND")
    STORAGE_BASE_PATH: Path = Field(
        default=Path("./runtime/storage"),
        env="STORAGE_BASE_PATH"
    )
    
    # Analysis Workspace
    ANALYSIS_WORKSPACE_PATH: Path = Field(
        default=Path("./runtime/analyses"),
        env="ANALYSIS_WORKSPACE_PATH"
    )
    
    # File Upload Limits
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS: List[str] = [".xlsx", ".xls", ".csv"]
    
    # ML Model Paths (relative to FinSight root)
    ML_MODEL_PATH: Path = Field(
        default=Path("../Model/models"),
        env="ML_MODEL_PATH"
    )
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

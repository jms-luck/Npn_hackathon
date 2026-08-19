from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Hire AI"
    api_prefix: str = "/api"
    frontend_dist_dir: str = str(ROOT_DIR / "frontend_dist")
    database_url: str = "sqlite:///./resume_screening.db"
    jwt_secret_key: str = Field(
        default="development-only-change-me",
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    default_admin_email: str | None = None
    default_admin_password: str | None = None
    log_dir: str = str(ROOT_DIR / "logs")
    log_level: str = "INFO"
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
    redis_url: str = "redis://localhost:6379/0"
    cache_default_ttl: int = 60
    cache_job_ttl: int = 30
    cache_company_ttl: int = 300
    cache_profile_ttl: int = 60
    cache_graph_ttl: int = 300
    cache_leetcode_ttl: int = 900
    cache_github_ttl: int = 3600
    github_token: str | None = None
    llm_explanations_per_match: int = 10
    github_evaluations_per_match: int = 50
    neo4j_uri: str | None = "bolt://localhost:7687"
    neo4j_username: str | None = "neo4j"
    neo4j_password: str | None = "hireai-graph-2026"

    azure_storage_connection_string: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AZURE_STORAGE_CONNECTION_STRING", "azure_blob_connection_string"
        ),
    )
    azure_storage_container: str = "resumes"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_embedding_deployment: str = Field(
        default="text-embedding-3-large",
        validation_alias=AliasChoices(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
            "AZURE_EMBEDDING_DEPLOYMENT",
            "Embeddings_Model",
        ),
    )
    azure_llm_deployment: str = Field(
        default="gpt-5.1",
        validation_alias=AliasChoices("AZURE_OPENAI_LLM_DEPLOYMENT", "Chat_Model"),
    )
    qdrant_url: str = Field(
        default="http://localhost:6333",
        validation_alias=AliasChoices("QDRANT_URL", "QDrant_EndPoint"),
    )
    qdrant_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("QDRANT_API_KEY", "QDrant_API"),
    )
    qdrant_job_collection: str = "job_embeddings"
    qdrant_resume_collection: str = "resume_embeddings"
    embedding_dimension: int = 3072
    auto_seed_external_indexes: bool = False
    skip_external_index_check: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
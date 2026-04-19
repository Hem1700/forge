from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://forge:forge@localhost:5432/forge"
    redis_url: str = "redis://localhost:6379"
    qdrant_url: str = "http://localhost:6333"
    neo4j_url: str = "bolt://localhost:17687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "forge_password"
    anthropic_api_key: str = ""
    use_local_llm: bool = False
    ollama_url: str = "http://localhost:11434"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    confidence_threshold: float = 0.75
    thread_death_threshold: int = 5
    frontend_url: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

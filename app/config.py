from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # === BANCO DE DADOS ===
    DB_HOST: str = Field(default="localhost", env="DB_HOST")
    DB_PORT: int = Field(default=5432, env="DB_PORT")
    DB_NAME: str = Field(default="wikisuporte2", env="DB_NAME")
    DB_USER: str = Field(default="postgres", env="DB_USER")
    DB_PASS: str = Field(default="", env="DB_PASS")

    # === JWT ===
    SECRET_KEY: str = Field(default="mude-esta-chave-em-producao", env="SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")

    # === GOTO CONNECT API ===
    GOTO_CLIENT_ID: str = Field(default="", env="GOTO_CLIENT_ID")
    GOTO_CLIENT_SECRET: str = Field(default="", env="GOTO_CLIENT_SECRET")
    GOTO_REFRESH_TOKEN: str = Field(default="", env="GOTO_REFRESH_TOKEN")

    # === GOOGLE GEMINI ===
    GEMINI_API_KEY: str = Field(default="", env="GEMINI_API_KEY")

    # === SISTEMA ===
    MODO_HEADLESS: bool = Field(default=True, env="MODO_HEADLESS")
    DEBUG: bool = Field(default=True, env="DEBUG")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASS}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

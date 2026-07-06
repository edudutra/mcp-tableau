"""Configuração e credenciais do MCP Tableau, lidas de variáveis de ambiente.

Toda credencial é carregada de env via `Settings` (Pydantic `BaseSettings`).
O segredo do PAT é mantido em `SecretStr`, de modo que nunca apareça em `repr`,
logs ou serializações acidentais.
"""

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcp_tableau.models import Thresholds


class ConfigError(RuntimeError):
    """Erro acionável de configuração (variável ausente/ inválida), sem segredos."""


class Settings(BaseSettings):
    """Configurações do servidor lidas de variáveis de ambiente.

    Variáveis obrigatórias: ``TABLEAU_SERVER_URL``, ``TABLEAU_PAT_NAME`` e
    ``TABLEAU_PAT_SECRET``. ``TABLEAU_SITE`` é opcional (vazio = site default do
    Tableau Server). Os limiares de complexidade têm defaults e podem ser
    sobrescritos por env.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Credenciais e destino (obrigatórias, exceto site)
    server_url: str = Field(validation_alias="TABLEAU_SERVER_URL")
    site: str = Field(default="", validation_alias="TABLEAU_SITE")
    pat_name: str = Field(validation_alias="TABLEAU_PAT_NAME")
    pat_secret: SecretStr = Field(validation_alias="TABLEAU_PAT_SECRET")

    # Tempo limite de requisições à API (segundos)
    request_timeout: int = Field(default=30, validation_alias="TABLEAU_TIMEOUT")

    # CA bundle opcional para verificação TLS (rede corporativa com CA própria).
    # Caminho para um arquivo PEM; vazio = usa o store padrão do `certifi`.
    ca_bundle: str = Field(default="", validation_alias="TABLEAU_CA_BUNDLE")

    # Limiares de complexidade (override por env)
    max_filters: int = Field(default=15, validation_alias="MAX_FILTERS")
    max_worksheets: int = Field(default=20, validation_alias="MAX_WORKSHEETS")
    max_data_sources: int = Field(default=5, validation_alias="MAX_DATA_SOURCES")

    # Limiares de volume das operações Hyper (override por env; defaults
    # conservadores). Exceder um limiar gera alerta não bloqueante, nunca bloqueio.
    hyper_max_source_file_mb: int = Field(
        default=500, validation_alias="HYPER_MAX_SOURCE_FILE_MB"
    )
    hyper_max_inline_rows: int = Field(
        default=1_000, validation_alias="HYPER_MAX_INLINE_ROWS"
    )
    hyper_max_result_rows: int = Field(
        default=200, validation_alias="HYPER_MAX_RESULT_ROWS"
    )
    hyper_max_extract_rows: int = Field(
        default=5_000_000, validation_alias="HYPER_MAX_EXTRACT_ROWS"
    )

    @property
    def thresholds(self) -> Thresholds:
        """Limiares efetivos de complexidade como contrato tipado."""
        return Thresholds(
            max_filters=self.max_filters,
            max_worksheets=self.max_worksheets,
            max_data_sources=self.max_data_sources,
        )


def load_settings() -> Settings:
    """Carrega e valida as configurações de ambiente.

    Em caso de variável obrigatória ausente ou inválida, levanta `ConfigError`
    com uma mensagem clara que identifica os campos problemáticos, **sem** expor
    qualquer valor sensível.
    """
    try:
        return Settings()  # type: ignore[call-arg]  # valores vêm do ambiente
    except ValidationError as exc:
        campos = ", ".join(
            str(erro["loc"][0]) for erro in exc.errors() if erro.get("loc")
        )
        raise ConfigError(
            "Configuração inválida do Tableau. Verifique as variáveis de ambiente "
            f"obrigatórias (campos: {campos}). Consulte .env.example."
        ) from exc

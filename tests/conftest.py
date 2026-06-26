"""Fixtures compartilhadas da suite de testes do MCP Tableau."""

import pytest

# Variáveis de ambiente obrigatórias para construir `Settings`.
_REQUIRED_ENV = {
    "TABLEAU_SERVER_URL": "https://tableau.example.com",
    "TABLEAU_SITE": "acme",
    "TABLEAU_PAT_NAME": "ci-token",
    "TABLEAU_PAT_SECRET": "s3cr3t-value-should-never-leak",
}

# Variáveis opcionais de limiar; limpas por padrão para testar os defaults.
_THRESHOLD_ENV = ("MAX_FILTERS", "MAX_WORKSHEETS", "MAX_DATA_SOURCES")


@pytest.fixture
def tableau_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Define as variáveis de ambiente obrigatórias e limpa os limiares.

    Garante isolamento: testes não dependem do ambiente real do desenvolvedor.
    Retorna o mapa de variáveis obrigatórias aplicadas.
    """
    for key, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    for key in _THRESHOLD_ENV:
        monkeypatch.delenv(key, raising=False)
    return dict(_REQUIRED_ENV)

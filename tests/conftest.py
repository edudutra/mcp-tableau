"""Fixtures compartilhadas da suite de testes do MCP Tableau."""

import os

import pytest

from mcp_tableau.config import Settings

# Variáveis de ambiente obrigatórias para construir `Settings`.
_REQUIRED_ENV = {
    "TABLEAU_SERVER_URL": "https://tableau.example.com",
    "TABLEAU_SITE": "acme",
    "TABLEAU_PAT_NAME": "ci-token",
    "TABLEAU_PAT_SECRET": "s3cr3t-value-should-never-leak",
}

# Variáveis opcionais de limiar; limpas por padrão para testar os defaults.
_THRESHOLD_ENV = ("MAX_FILTERS", "MAX_WORKSHEETS", "MAX_DATA_SOURCES")


@pytest.fixture(autouse=True)
def _isolate_settings_env(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isola a suite rápida do ambiente real e do `.env` do projeto.

    Sem isto, `Settings` leria o arquivo `.env` do desenvolvedor (e variáveis
    `TABLEAU_*` exportadas no shell), tornando os testes dependentes da máquina
    local — ex.: `TABLEAU_CA_BUNDLE` ou limiares vazariam para os asserts.

    Os testes de integração (`@pytest.mark.integration`) são preservados: eles
    dependem do ambiente real (credenciais e sandbox) e ficam de fora deste
    isolamento.
    """
    if "integration" in request.keywords:
        return
    # Não ler o `.env` do projeto durante a suite rápida.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # Remove qualquer TABLEAU_*/limiar herdado do shell do desenvolvedor.
    for key in list(os.environ):
        if key.startswith("TABLEAU_") or key in _THRESHOLD_ENV:
            monkeypatch.delenv(key, raising=False)


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

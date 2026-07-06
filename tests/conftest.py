"""Fixtures compartilhadas da suite de testes do MCP Tableau."""

import os
from pathlib import Path

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
def hyper_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Ambiente Hyper com limiares de volume propositalmente baixos.

    Permite exercitar `VolumeAlert`/`warnings` sem arquivos grandes ou milhões de
    linhas: um arquivo minúsculo já excede `HYPER_MAX_SOURCE_FILE_MB=0` e poucas
    linhas excedem os limiares inline/extração. Inclui as credenciais
    obrigatórias para que `load_settings()` real construa o `Settings`.
    """
    env = {
        **_REQUIRED_ENV,
        "HYPER_MAX_SOURCE_FILE_MB": "0",
        "HYPER_MAX_INLINE_ROWS": "2",
        "HYPER_MAX_RESULT_ROWS": "100",
        "HYPER_MAX_EXTRACT_ROWS": "5",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return dict(env)


@pytest.fixture
def sample_hyper(tmp_path: Path) -> Path:
    """Constrói um `.hyper` mínimo (tabela única `Extract.Extract`) sob demanda.

    Reuso **apenas** nos testes `integration`: exige o runtime real do
    `tableauhyperapi` (ausente na suite rápida). Uma única tabela no schema/tabela
    `Extract.Extract` mantém compatibilidade com Tableau Server antigos e basta
    para publicar/inspecionar. O arquivo vive em `tmp_path` — nada versionado.
    """
    from mcp_tableau.hyper.engine import InlineIngestRequest, hyper_session
    from mcp_tableau.models import InlineColumn

    dest = tmp_path / "sample.hyper"
    with hyper_session() as engine:
        engine.create_table_from_rows(
            InlineIngestRequest(
                hyper_path=dest,
                table_name="Extract",
                columns=[
                    InlineColumn(name="cidade", type="text"),
                    InlineColumn(name="vendas", type="big_int"),
                ],
                rows=[["Santos", 100], ["Sao Paulo", 200]],
            )
        )
    return dest


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

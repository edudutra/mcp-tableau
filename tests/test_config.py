"""Testes unitários de `mcp_tableau.config`."""

import pytest

from mcp_tableau.config import ConfigError, Settings, load_settings


def test_settings_carrega_variaveis_obrigatorias(
    tableau_env: dict[str, str],
) -> None:
    settings = load_settings()

    assert settings.server_url == tableau_env["TABLEAU_SERVER_URL"]
    assert settings.site == tableau_env["TABLEAU_SITE"]
    assert settings.pat_name == tableau_env["TABLEAU_PAT_NAME"]
    assert settings.pat_secret.get_secret_value() == tableau_env["TABLEAU_PAT_SECRET"]


def test_settings_variavel_faltante_levanta_erro_claro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("TABLEAU_SERVER_URL", "TABLEAU_PAT_NAME", "TABLEAU_PAT_SECRET"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_settings()

    mensagem = str(exc_info.value)
    # Erro acionável aponta as variáveis faltantes, sem vazar valores sensíveis.
    assert "TABLEAU_SERVER_URL" in mensagem
    assert "TABLEAU_PAT_SECRET" in mensagem
    assert "s3cr3t" not in mensagem


def test_settings_thresholds_default_quando_env_ausente(
    tableau_env: dict[str, str],
) -> None:
    thresholds = load_settings().thresholds

    assert thresholds.max_filters == 15
    assert thresholds.max_worksheets == 20
    assert thresholds.max_data_sources == 5


def test_settings_thresholds_override_por_env(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_FILTERS", "30")
    monkeypatch.setenv("MAX_WORKSHEETS", "40")
    monkeypatch.setenv("MAX_DATA_SOURCES", "8")

    thresholds = load_settings().thresholds

    assert thresholds.max_filters == 30
    assert thresholds.max_worksheets == 40
    assert thresholds.max_data_sources == 8


def test_settings_secret_nao_aparece_em_repr(tableau_env: dict[str, str]) -> None:
    settings = load_settings()

    # SecretStr garante que o valor não vaza em repr/str da configuração.
    assert tableau_env["TABLEAU_PAT_SECRET"] not in repr(settings)
    assert isinstance(settings, Settings)

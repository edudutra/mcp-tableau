"""Testes unitários de `mcp_tableau.config`."""

from pathlib import Path

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
    tmp_path: Path,
) -> None:
    # Regressão BUG-01: o teste precisa ser hermético. Sem isolar o `env_file`, um
    # `.env` real na raiz do repo repovoa as credenciais e o erro não ocorre
    # ("DID NOT RAISE"). `chdir` para um diretório sem `.env` neutraliza essa leitura
    # (o `Settings` resolve `env_file=".env"` relativo ao cwd).
    monkeypatch.chdir(tmp_path)
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


def test_settings_ca_bundle_default_vazio(tableau_env: dict[str, str]) -> None:
    # Sem TABLEAU_CA_BUNDLE, usa-se o store padrão do certifi (string vazia).
    assert load_settings().ca_bundle == ""


def test_settings_ca_bundle_override_por_env(
    tableau_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TABLEAU_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt")

    assert load_settings().ca_bundle == "/etc/ssl/certs/ca-certificates.crt"


def test_settings_secret_nao_aparece_em_repr(tableau_env: dict[str, str]) -> None:
    settings = load_settings()

    # SecretStr garante que o valor não vaza em repr/str da configuração.
    assert tableau_env["TABLEAU_PAT_SECRET"] not in repr(settings)
    assert isinstance(settings, Settings)


_HYPER_THRESHOLD_ENV = (
    "HYPER_MAX_SOURCE_FILE_MB",
    "HYPER_MAX_INLINE_ROWS",
    "HYPER_MAX_RESULT_ROWS",
    "HYPER_MAX_EXTRACT_ROWS",
)


def test_settings_hyper_defaults_conservadores(
    tableau_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in _HYPER_THRESHOLD_ENV:
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()

    assert settings.hyper_max_source_file_mb == 500
    assert settings.hyper_max_inline_rows == 1_000
    assert settings.hyper_max_result_rows == 200
    assert settings.hyper_max_extract_rows == 5_000_000


def test_settings_hyper_limiares_lidos_do_ambiente(
    tableau_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYPER_MAX_SOURCE_FILE_MB", "10")
    monkeypatch.setenv("HYPER_MAX_INLINE_ROWS", "50")
    monkeypatch.setenv("HYPER_MAX_RESULT_ROWS", "20")
    monkeypatch.setenv("HYPER_MAX_EXTRACT_ROWS", "100")

    settings = load_settings()

    assert settings.hyper_max_source_file_mb == 10
    assert settings.hyper_max_inline_rows == 50
    assert settings.hyper_max_result_rows == 20
    assert settings.hyper_max_extract_rows == 100


def test_settings_hyper_limiar_invalido_gera_config_error_sem_segredos(
    tableau_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYPER_MAX_INLINE_ROWS", "não-é-número")

    with pytest.raises(ConfigError) as exc_info:
        load_settings()

    mensagem = str(exc_info.value)
    # Erro acionável identifica a variável, sem vazar o valor sensível do PAT.
    assert "HYPER_MAX_INLINE_ROWS" in mensagem
    assert tableau_env["TABLEAU_PAT_SECRET"] not in mensagem

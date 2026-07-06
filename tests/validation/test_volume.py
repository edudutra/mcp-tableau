"""Testes unitários das salvaguardas puras de volume (`validation/volume.py`)."""

from pathlib import Path

import pytest

from mcp_tableau.config import load_settings
from mcp_tableau.validation.volume import (
    check_extracted_rows,
    check_inline_rows,
    check_source_file,
)

_MB = 1024 * 1024


def test_check_source_file_abaixo_do_limiar_retorna_lista_vazia(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HYPER_MAX_SOURCE_FILE_MB", "1")
    settings = load_settings()
    arquivo = tmp_path / "pequeno.csv"
    arquivo.write_bytes(b"\0" * 1024)  # 1 KB

    assert check_source_file(arquivo, settings) == []


def test_check_source_file_acima_do_limiar_retorna_dimensao_source_file_mb(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HYPER_MAX_SOURCE_FILE_MB", "1")
    settings = load_settings()
    arquivo = tmp_path / "grande.csv"
    arquivo.write_bytes(b"\0" * (2 * _MB))

    dimensoes = check_source_file(arquivo, settings)

    assert len(dimensoes) == 1
    assert dimensoes[0].dimension == "source_file_mb"
    assert dimensoes[0].actual == pytest.approx(2.0)
    assert dimensoes[0].limit == 1.0


def test_check_source_file_exatamente_no_limiar_nao_excede(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HYPER_MAX_SOURCE_FILE_MB", "1")
    settings = load_settings()
    arquivo = tmp_path / "exato.csv"
    arquivo.write_bytes(b"\0" * _MB)  # exatamente 1 MB

    assert check_source_file(arquivo, settings) == []


def test_check_inline_rows_abaixo_do_limiar_retorna_lista_vazia(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYPER_MAX_INLINE_ROWS", "1000")
    settings = load_settings()

    assert check_inline_rows(999, settings) == []


def test_check_inline_rows_acima_do_limiar_retorna_dimensao_inline_rows(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYPER_MAX_INLINE_ROWS", "1000")
    settings = load_settings()

    dimensoes = check_inline_rows(1001, settings)

    assert len(dimensoes) == 1
    assert dimensoes[0].dimension == "inline_rows"
    assert dimensoes[0].actual == 1001.0
    assert dimensoes[0].limit == 1000.0


def test_check_extracted_rows_acima_do_limiar_retorna_dimensao_extracted_rows(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYPER_MAX_EXTRACT_ROWS", "5000")
    settings = load_settings()

    dimensoes = check_extracted_rows(5001, settings)

    assert len(dimensoes) == 1
    assert dimensoes[0].dimension == "extracted_rows"
    assert dimensoes[0].actual == 5001.0


def test_check_extracted_rows_abaixo_do_limiar_retorna_lista_vazia(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYPER_MAX_EXTRACT_ROWS", "5000")
    settings = load_settings()

    assert check_extracted_rows(5000, settings) == []


def test_dimensao_excedida_inclui_limit_actual_e_risk_preenchidos(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYPER_MAX_INLINE_ROWS", "10")
    settings = load_settings()

    dimensao = check_inline_rows(20, settings)[0]

    assert dimensao.limit == 10.0
    assert dimensao.actual == 20.0
    assert dimensao.risk  # mensagem de risco não vazia


def test_limiares_customizados_via_settings_sao_respeitados(
    tableau_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYPER_MAX_INLINE_ROWS", "5")
    settings = load_settings()

    # Com limiar baixo customizado, 6 linhas excedem; 4 permanecem dentro.
    assert check_inline_rows(6, settings)
    assert check_inline_rows(4, settings) == []

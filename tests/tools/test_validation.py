"""Testes unitários do validador compartilhado de caminho de saída.

`require_output_destination` (tools/_validation.py) é uma função pura: apenas
checagens locais de extensão e existência do diretório-pai, sem rede nem cliente
Tableau. Usa `tmp_path` para exercitar diretórios reais existentes/inexistentes.
"""

from __future__ import annotations

from pathlib import Path

from mcp_tableau.models import ErrorCode, ToolError
from mcp_tableau.tools._validation import require_output_destination


def test_require_output_destination_extensao_unica_correta_retorna_none(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chart.png"
    assert require_output_destination(path, {".png"}) is None


def test_require_output_destination_extensao_de_conjunto_multiplo_retorna_none(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chart.jpg"
    assert require_output_destination(path, {".png", ".jpg"}) is None


def test_require_output_destination_extensao_case_insensitive_retorna_none(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chart.PNG"
    assert require_output_destination(path, {".png"}) is None


def test_require_output_destination_extensao_errada_retorna_validation_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chart.txt"
    result = require_output_destination(path, {".png"})
    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    assert ".png" in result.error.message
    assert ".txt" in result.error.message
    assert str(path) in result.error.message


def test_require_output_destination_extensao_errada_lista_todos_sufixos_esperados(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chart.txt"
    result = require_output_destination(path, {".png", ".jpg"})
    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    assert ".png" in result.error.message
    assert ".jpg" in result.error.message


def test_require_output_destination_pai_inexistente_retorna_validation_error(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "missing"
    path = parent / "chart.png"
    result = require_output_destination(path, {".png"})
    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    assert str(parent) in result.error.message


def test_require_output_destination_extensao_errada_e_pai_ausente_extensao_vence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing" / "chart.txt"
    result = require_output_destination(path, {".png"})
    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    assert "extensão" in result.error.message
    assert "não existe" not in result.error.message

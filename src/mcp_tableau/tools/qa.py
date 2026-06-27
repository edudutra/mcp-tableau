"""Ferramentas MCP da Capacidade 3 (QA): inspeção estrutural e complexidade.

Ferramentas finas que baixam o workbook publicado via `TableauClient` e delegam a
análise às funções puras de `validation/`: `inspect_workbook_structure` reporta a
estrutura interna e os `issues` detectados (campos quebrados, filtros sem lógica,
conexões inválidas); `audit_workbook_complexity` audita as métricas contra os
limiares de `Settings`. O objetivo é diagnóstico, não bloqueio — a presença de
`issues` não falha a ferramenta.

NOTA (MVP): o 7_task previa combinar com a Metadata API para campos quebrados
resolvidos pelo servidor, mas a camada de metadados atual não expõe essa consulta
e a inspeção estrutural local (XML) já detecta os `issues`. Portanto a base aqui é
`inspect_structure` sobre o arquivo baixado; nenhum método inexistente é invocado.

O acesso ao Tableau acontece exclusivamente via `tableau/client.py`; o registro no
servidor FastMCP é feito por `register(mcp)`, chamado por `server.py`.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastmcp import FastMCP

from mcp_tableau.config import load_settings
from mcp_tableau.models import ComplexityReport, ErrorCode, StructureReport, ToolError
from mcp_tableau.tableau.client import (
    TableauClient,
    TableauClientError,
    tableau_session,
)
from mcp_tableau.validation.complexity import audit_complexity
from mcp_tableau.validation.structure import StructureParseError, inspect_structure

logger = logging.getLogger(__name__)


def inspect_workbook_structure(workbook_id: str) -> StructureReport | ToolError:
    """Inspeciona a estrutura interna de um workbook publicado no Tableau.

    Baixa o artefato do workbook do servidor, parseia o XML local e reporta
    worksheets, dashboards, conexões, campos e filtros, além de uma lista de
    `issues` (campos quebrados, filtros sem lógica, conexões inválidas). A
    presença de `issues` é diagnóstica e **não** faz a ferramenta falhar: o
    relatório é retornado com `issues` populado.

    Worksheets e dashboards são retornados como objetos `{id, name}`: o `id` é o
    LUID renderizável da view (aceito diretamente por `render_view_image`/
    `render_view_pdf`), obtido por correspondência de nome com as views
    publicadas do workbook. Os filtros expõem `worksheet_id` com o LUID da
    worksheet onde estão declarados. Quando uma sheet não é uma view publicada
    (ex.: oculta) ou quando a consulta de views falha, o `id`/`worksheet_id`
    correspondente vem `null` (campo presente, não omitido) — o enriquecimento é
    **best-effort** e nunca transforma a inspeção em erro.

    Args:
        workbook_id: LUID do workbook publicado no Tableau.

    Returns:
        `StructureReport` em caso de sucesso (inclusive no caminho degradado, com
        ids `null` e `status="success"`), ou `ToolError` com código acionável
        (`NOT_FOUND` se o workbook não existir, `UPSTREAM_ERROR` se o artefato
        baixado for inválido/corrompido, ou demais códigos da camada de
        integração: `AUTH_FAILED`, `PERMISSION_DENIED`, ...).
    """
    try:
        with tableau_session(load_settings()) as client:
            report = _load_structure(client, workbook_id)
            return _enrich_with_view_luids(client, report, workbook_id)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)
    except StructureParseError as exc:
        return ToolError.of(ErrorCode.UPSTREAM_ERROR, str(exc))


def audit_workbook_complexity(workbook_id: str) -> ComplexityReport | ToolError:
    """Audita os indicadores de complexidade de um workbook contra boas práticas.

    Baixa e parseia o workbook (como `inspect_workbook_structure`) e compara as
    métricas medidas (worksheets, filtros, fontes de dados) com os limiares
    configurados em `Settings`. Sinaliza riscos de performance em `findings` e
    define `compliant=false` quando algum limiar é excedido.

    Args:
        workbook_id: LUID do workbook publicado no Tableau.

    Returns:
        `ComplexityReport` em caso de sucesso, ou `ToolError` com código acionável
        (`NOT_FOUND` se o workbook não existir, `UPSTREAM_ERROR` se o artefato for
        inválido/corrompido, ou demais códigos da camada de integração).
    """
    try:
        settings = load_settings()
        with tableau_session(settings) as client:
            report = _load_structure(client, workbook_id)
            return audit_complexity(
                report, settings.thresholds, workbook_id=workbook_id
            )
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)
    except StructureParseError as exc:
        return ToolError.of(ErrorCode.UPSTREAM_ERROR, str(exc))


def _load_structure(client: TableauClient, workbook_id: str) -> StructureReport:
    """Baixa o workbook para um diretório temporário e o inspeciona.

    Centraliza o fluxo comum das duas tools: download via `TableauClient` e
    parsing estrutural puro. Pode levantar `TableauClientError` (download) ou
    `StructureParseError` (parsing), tratados pelas tools chamadoras.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        path = client.download_workbook(workbook_id, Path(tmpdir))
        return inspect_structure(path, workbook_id=workbook_id)


def _enrich_with_view_luids(
    client: TableauClient, report: StructureReport, workbook_id: str
) -> StructureReport:
    """Preenche `SheetRef.id` e `FilterInfo.worksheet_id` por nome (best-effort).

    Consulta as views publicadas do workbook (`list_workbook_view_luids`) e casa
    cada worksheet/dashboard e filtro com o LUID da view de mesmo nome. Sheets sem
    view publicada (ex.: ocultas) permanecem com `id=None`.

    O enriquecimento é **best-effort** (RF10): qualquer `TableauClientError` ao
    obter as views degrada o relatório para ids nulos e o retorna com
    `status="success"`, sem propagar erro. Nenhuma credencial é registrada em log.
    """
    try:
        luid_by_name = client.list_workbook_view_luids(workbook_id)
    except TableauClientError as exc:
        logger.warning(
            "Enriquecimento de LUIDs indisponível para o workbook %s (%s); "
            "worksheets/dashboards/filtros retornarão com id nulo.",
            workbook_id,
            exc.code.value,
        )
        return report

    sheets = [*report.worksheets, *report.dashboards]
    for sheet in sheets:
        sheet.id = luid_by_name.get(sheet.name)
    for filtro in report.filters:
        filtro.worksheet_id = luid_by_name.get(filtro.worksheet)

    missing = sum(1 for sheet in sheets if sheet.id is None)
    logger.debug(
        "Workbook %s: %d de %d sheet(s) sem LUID de view correspondente.",
        workbook_id,
        missing,
        len(sheets),
    )
    return report


def register(mcp: FastMCP) -> None:
    """Registra as ferramentas de QA na instância FastMCP."""
    mcp.tool(inspect_workbook_structure)
    mcp.tool(audit_workbook_complexity)

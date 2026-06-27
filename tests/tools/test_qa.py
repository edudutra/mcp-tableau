"""Testes unitários das ferramentas de QA (`tools/qa.py`).

`tableau_session`, `load_settings` e `inspect_structure` são mockados: não há rede
nem parsing de um `.twbx` real. O foco é a orquestração (download + análise) e o
mapeamento de erros para o envelope `ToolError`.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_tableau.models import (
    ComplexityReport,
    ConnectionInfo,
    ErrorCode,
    FilterInfo,
    SheetRef,
    StructureIssue,
    StructureReport,
    Thresholds,
    ToolError,
)
from mcp_tableau.tableau.client import TableauClientError
from mcp_tableau.tools import qa
from mcp_tableau.validation.structure import StructureParseError

WORKBOOK_ID = "wb-123"


def _make_settings(thresholds: Thresholds) -> MagicMock:
    """Settings falso cujo atributo `thresholds` devolve os limiares informados."""
    settings = MagicMock(name="Settings")
    settings.thresholds = thresholds
    return settings


def _patch_session(monkeypatch: pytest.MonkeyPatch, client: MagicMock) -> None:
    """Substitui `qa.tableau_session` por um context manager que entrega `client`."""

    @contextlib.contextmanager
    def fake_session(_settings: object):
        yield client

    monkeypatch.setattr(qa, "tableau_session", fake_session)


def _client_returning(path: Path) -> MagicMock:
    """Client mock cujo `download_workbook` retorna o `path` informado.

    O mapa de LUIDs nasce vazio: sem correspondência, os ids permanecem `None`.
    Testes de enriquecimento sobrescrevem `list_workbook_view_luids`.
    """
    client = MagicMock(name="TableauClient")
    client.download_workbook.return_value = path
    client.list_workbook_view_luids.return_value = {}
    return client


def test_inspect_workbook_structure_baixa_e_parseia_retorna_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact = tmp_path / "wb.twbx"
    client = _client_returning(artifact)
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))

    report = StructureReport(
        workbook_id=WORKBOOK_ID,
        worksheets=[SheetRef(name="Vendas"), SheetRef(name="Resumo")],
        connections=[ConnectionInfo(name="pg", type="postgres", is_valid=True)],
    )
    captured: dict[str, object] = {}

    def fake_inspect(path: Path, workbook_id: str = "") -> StructureReport:
        captured["path"] = path
        captured["workbook_id"] = workbook_id
        return report

    monkeypatch.setattr(qa, "inspect_structure", fake_inspect)

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    assert result is report
    assert [w.name for w in result.worksheets] == ["Vendas", "Resumo"]
    client.download_workbook.assert_called_once()
    # O download usa um diretório temporário como destino.
    download_dir = client.download_workbook.call_args.args[1]
    assert isinstance(download_dir, Path)
    assert captured["path"] == artifact
    assert captured["workbook_id"] == WORKBOOK_ID


def test_inspect_workbook_structure_workbook_inexistente_retorna_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(name="TableauClient")
    client.download_workbook.side_effect = TableauClientError(
        ErrorCode.NOT_FOUND, "Recurso não encontrado no Tableau."
    )
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))
    monkeypatch.setattr(
        qa,
        "inspect_structure",
        lambda *a, **k: pytest.fail("inspect_structure não deveria ser chamado"),
    )

    result = qa.inspect_workbook_structure("missing-wb")

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.NOT_FOUND


def test_inspect_workbook_structure_issues_nao_falham_ferramenta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))

    report = StructureReport(
        workbook_id=WORKBOOK_ID,
        filters=[
            FilterInfo(
                worksheet="Vendas", field="Região", kind="categorical", has_logic=False
            )
        ],
        issues=[
            StructureIssue(
                code="filter_no_logic",
                severity="warning",
                target="Vendas:Região",
                detail="Filtro sem condição.",
            )
        ],
    )
    monkeypatch.setattr(qa, "inspect_structure", lambda *a, **k: report)

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    assert isinstance(result, StructureReport)
    assert result.status == "success"
    assert len(result.issues) == 1
    assert result.issues[0].code == "filter_no_logic"


def test_inspect_workbook_structure_arquivo_invalido_retorna_upstream_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))

    def boom(*_a: object, **_k: object) -> StructureReport:
        raise StructureParseError("Workbook corrompido.")

    monkeypatch.setattr(qa, "inspect_structure", boom)

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.UPSTREAM_ERROR


def test_audit_workbook_complexity_retorna_compliant_conforme_metricas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))

    # Estrutura enxuta, bem abaixo dos limiares -> compliant=True, sem findings.
    report = StructureReport(
        workbook_id=WORKBOOK_ID, worksheets=[SheetRef(name="A"), SheetRef(name="B")]
    )
    monkeypatch.setattr(qa, "inspect_structure", lambda *a, **k: report)

    result = qa.audit_workbook_complexity(WORKBOOK_ID)

    assert isinstance(result, ComplexityReport)
    assert result.compliant is True
    assert result.findings == []
    assert result.metrics.worksheets == 2
    assert result.workbook_id == WORKBOOK_ID


def test_audit_workbook_complexity_usa_thresholds_de_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    _patch_session(monkeypatch, client)

    # Limiares baixíssimos vindos da config: 1 worksheet máx.
    low = Thresholds(max_filters=0, max_worksheets=1, max_data_sources=0)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(low))

    # Métricas acima dos limiares -> deve excedê-los e ficar não-conforme.
    report = StructureReport(
        workbook_id=WORKBOOK_ID,
        worksheets=[SheetRef(name="A"), SheetRef(name="B"), SheetRef(name="C")],
        connections=[ConnectionInfo(name="pg", type="postgres", is_valid=True)],
        filters=[
            FilterInfo(
                worksheet="A", field="Região", kind="categorical", has_logic=True
            )
        ],
    )
    monkeypatch.setattr(qa, "inspect_structure", lambda *a, **k: report)

    result = qa.audit_workbook_complexity(WORKBOOK_ID)

    assert isinstance(result, ComplexityReport)
    assert result.thresholds == low
    assert result.compliant is False
    exceeded = {finding.metric for finding in result.findings}
    assert exceeded == {"worksheets", "filters", "data_sources"}


def _thresholds() -> Thresholds:
    """Limiares folgados o suficiente para não disparar findings por padrão."""
    return Thresholds(max_filters=15, max_worksheets=20, max_data_sources=5)


# -- Enriquecimento de LUIDs por nome (Tarefa 4.0) -----------------------------


def _structure_report() -> StructureReport:
    """Relatório com sheets/filtros para exercitar o merge nome -> LUID."""
    return StructureReport(
        workbook_id=WORKBOOK_ID,
        worksheets=[SheetRef(name="Vendas por Região"), SheetRef(name="Oculta")],
        dashboards=[SheetRef(name="Painel Executivo")],
        filters=[
            FilterInfo(
                worksheet="Vendas por Região",
                field="Região",
                kind="categorical",
                has_logic=True,
            )
        ],
    )


def _patched_inspect(monkeypatch: pytest.MonkeyPatch, report: StructureReport) -> None:
    monkeypatch.setattr(qa, "inspect_structure", lambda *a, **k: report)


def test_inspect_structure_enriquece_ids_por_nome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    client.list_workbook_view_luids.return_value = {
        "Vendas por Região": "luid-vendas",
        "Painel Executivo": "luid-painel",
    }
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))
    _patched_inspect(monkeypatch, _structure_report())

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    assert isinstance(result, StructureReport)
    by_name = {w.name: w.id for w in result.worksheets}
    assert by_name["Vendas por Região"] == "luid-vendas"
    assert result.dashboards[0].id == "luid-painel"
    assert result.filters[0].worksheet_id == "luid-vendas"
    client.list_workbook_view_luids.assert_called_once_with(WORKBOOK_ID)


def test_inspect_structure_sheet_sem_correspondencia_id_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    client.list_workbook_view_luids.return_value = {"Vendas por Região": "luid-vendas"}
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))
    _patched_inspect(monkeypatch, _structure_report())

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    assert isinstance(result, StructureReport)
    oculta = next(w for w in result.worksheets if w.name == "Oculta")
    assert oculta.id is None


def test_inspect_structure_filtro_worksheet_id_preenchido(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    client.list_workbook_view_luids.return_value = {"Vendas por Região": "luid-vendas"}
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))
    _patched_inspect(monkeypatch, _structure_report())

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    assert isinstance(result, StructureReport)
    assert result.filters[0].worksheet_id == "luid-vendas"


def test_inspect_structure_degrada_quando_populate_views_falha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    client.list_workbook_view_luids.side_effect = TableauClientError(
        ErrorCode.UPSTREAM_ERROR, "Falha ao comunicar com o Tableau."
    )
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))
    _patched_inspect(monkeypatch, _structure_report())

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    assert isinstance(result, StructureReport)
    assert result.status == "success"
    assert all(w.id is None for w in result.worksheets)
    assert all(d.id is None for d in result.dashboards)
    assert result.filters[0].worksheet_id is None


def test_inspect_structure_degrada_quando_metadata_indisponivel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    client.list_workbook_view_luids.side_effect = TableauClientError(
        ErrorCode.NOT_FOUND, "Recurso não encontrado no Tableau."
    )
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))
    _patched_inspect(monkeypatch, _structure_report())

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    # Falha no enriquecimento NÃO vira ToolError: degrada para ids nulos.
    assert isinstance(result, StructureReport)
    assert result.status == "success"
    assert all(w.id is None for w in result.worksheets)


def test_inspect_structure_not_found_antes_do_enriquecimento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(name="TableauClient")
    client.download_workbook.side_effect = TableauClientError(
        ErrorCode.NOT_FOUND, "Recurso não encontrado no Tableau."
    )
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))
    monkeypatch.setattr(
        qa,
        "inspect_structure",
        lambda *a, **k: pytest.fail("inspect_structure não deveria ser chamado"),
    )

    result = qa.inspect_workbook_structure("missing-wb")

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.NOT_FOUND
    # Download falhou antes: o enriquecimento nunca é chamado.
    client.list_workbook_view_luids.assert_not_called()


def test_inspect_structure_id_aceito_por_render(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    client.list_workbook_view_luids.return_value = {"Vendas por Região": "luid-vendas"}
    _patch_session(monkeypatch, client)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(_thresholds()))
    _patched_inspect(monkeypatch, _structure_report())

    result = qa.inspect_workbook_structure(WORKBOOK_ID)

    assert isinstance(result, StructureReport)
    enriquecido = next(w for w in result.worksheets if w.name == "Vendas por Região")
    # O id é exatamente o LUID do mapa, sem transformação: o formato aceito por
    # render_view_image(view_id: str).
    assert isinstance(enriquecido.id, str)
    assert enriquecido.id == "luid-vendas"


def test_audit_complexity_inalterado_com_sheetref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = _client_returning(tmp_path / "wb.twbx")
    _patch_session(monkeypatch, client)
    low = Thresholds(max_filters=0, max_worksheets=1, max_data_sources=5)
    monkeypatch.setattr(qa, "load_settings", lambda: _make_settings(low))
    _patched_inspect(monkeypatch, _structure_report())

    result = qa.audit_workbook_complexity(WORKBOOK_ID)

    assert isinstance(result, ComplexityReport)
    assert result.metrics.worksheets == 2
    assert result.metrics.dashboards == 1
    assert result.compliant is False
    # Auditoria não chama enriquecimento (só conta sobre SheetRef).
    client.list_workbook_view_luids.assert_not_called()

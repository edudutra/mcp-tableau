"""Testes da inspeção estrutural pura de workbooks (`validation/structure.py`)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from mcp_tableau.validation.structure import StructureParseError, inspect_structure


def _workbook_xml(
    *,
    columns: str,
    worksheets: str,
    dashboards: str,
    connection: str = (
        "<connection class='federated'>"
        "<named-connections><named-connection caption='db' name='nc1'>"
        "<connection class='postgres' dbname='vendas' server='db.example.com' />"
        "</named-connection></named-connections></connection>"
    ),
) -> str:
    """Monta um XML mínimo válido de workbook Tableau."""
    return (
        "<?xml version='1.0' encoding='utf-8' ?>\n"
        "<workbook version='18.1' "
        "xmlns:user='http://www.tableausoftware.com/xml/user'>"
        "<datasources>"
        "<datasource caption='Vendas' name='federated.abc' version='18.1'>"
        f"{connection}{columns}"
        "</datasource>"
        "</datasources>"
        f"<worksheets>{worksheets}</worksheets>"
        f"<dashboards>{dashboards}</dashboards>"
        "</workbook>"
    )


_COLUMNS_BASIC = (
    "<column caption='Receita' datatype='real' name='[Receita]' "
    "role='measure' type='quantitative' />"
    "<column caption='Regiao' datatype='string' name='[Regiao]' "
    "role='dimension' type='nominal' />"
)

_COLUMN_CALC_OK = (
    "<column caption='Margem' datatype='real' name='[Margem]' "
    "role='measure' type='quantitative'>"
    "<calculation class='tableau' formula='[Receita] * 0.2' />"
    "</column>"
)

_COLUMN_CALC_BROKEN = (
    "<column caption='Quebrado' datatype='real' name='[Quebrado]' "
    "role='measure' type='quantitative'>"
    "<calculation class='tableau' formula='[Inexistente] + 1' />"
    "</column>"
)

_WORKSHEET_WITH_LOGIC = (
    "<worksheet name='Sheet 1'><table><view>"
    "<filter class='quantitative' column='[federated.abc].[Receita]'>"
    "<min>0</min><max>100</max></filter>"
    "</view></table></worksheet>"
)

_WORKSHEET_NO_LOGIC = (
    "<worksheet name='Sheet 1'><table><view>"
    "<filter class='categorical' column='[federated.abc].[Regiao]'></filter>"
    "</view></table></worksheet>"
)

_DASHBOARD = "<dashboard name='Dashboard 1'><zones/></dashboard>"


def _write_twb(tmp_path: Path, xml: str, name: str = "wb.twb") -> Path:
    path = tmp_path / name
    path.write_text(xml, encoding="utf-8")
    return path


def _write_twbx(tmp_path: Path, xml: str, name: str = "wb.twbx") -> Path:
    inner = tmp_path / "_inner.twb"
    inner.write_text(xml, encoding="utf-8")
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(inner, arcname="wb.twb")
    return path


def test_inspect_structure_workbook_valido_lista_worksheets_e_dashboards(
    tmp_path: Path,
) -> None:
    xml = _workbook_xml(
        columns=_COLUMNS_BASIC,
        worksheets=_WORKSHEET_WITH_LOGIC,
        dashboards=_DASHBOARD,
    )
    report = inspect_structure(_write_twb(tmp_path, xml))

    assert report.worksheets == ["Sheet 1"]
    assert report.dashboards == ["Dashboard 1"]


def test_inspect_structure_extrai_campos_calculados_com_formula(
    tmp_path: Path,
) -> None:
    xml = _workbook_xml(
        columns=_COLUMNS_BASIC + _COLUMN_CALC_OK,
        worksheets=_WORKSHEET_WITH_LOGIC,
        dashboards=_DASHBOARD,
    )
    report = inspect_structure(_write_twb(tmp_path, xml))

    calculados = [f for f in report.fields if f.is_calculated]
    assert len(calculados) == 1
    assert calculados[0].name == "Margem"
    assert calculados[0].formula == "[Receita] * 0.2"
    assert calculados[0].is_broken is False


def test_inspect_structure_campo_calculado_referencia_inexistente_marca_broken_field(
    tmp_path: Path,
) -> None:
    xml = _workbook_xml(
        columns=_COLUMNS_BASIC + _COLUMN_CALC_BROKEN,
        worksheets=_WORKSHEET_WITH_LOGIC,
        dashboards=_DASHBOARD,
    )
    report = inspect_structure(_write_twb(tmp_path, xml))

    quebrado = next(f for f in report.fields if f.name == "Quebrado")
    assert quebrado.is_broken is True
    codes = {(i.code, i.severity, i.target) for i in report.issues}
    assert ("broken_field", "error", "Quebrado") in codes


def test_inspect_structure_filtro_sem_logica_gera_issue_warning(
    tmp_path: Path,
) -> None:
    xml = _workbook_xml(
        columns=_COLUMNS_BASIC,
        worksheets=_WORKSHEET_NO_LOGIC,
        dashboards=_DASHBOARD,
    )
    report = inspect_structure(_write_twb(tmp_path, xml))

    no_logic = [i for i in report.issues if i.code == "filter_no_logic"]
    assert len(no_logic) == 1
    assert no_logic[0].severity == "warning"
    assert any(f.has_logic is False for f in report.filters)


def test_inspect_structure_conexao_invalida_gera_issue(tmp_path: Path) -> None:
    # Conexão a banco sem servidor declarado => inválida.
    connection = (
        "<connection class='federated'>"
        "<named-connections><named-connection caption='db' name='nc1'>"
        "<connection class='postgres' dbname='vendas' />"
        "</named-connection></named-connections></connection>"
    )
    xml = _workbook_xml(
        columns=_COLUMNS_BASIC,
        worksheets=_WORKSHEET_WITH_LOGIC,
        dashboards=_DASHBOARD,
        connection=connection,
    )
    report = inspect_structure(_write_twb(tmp_path, xml))

    invalid = [c for c in report.connections if not c.is_valid]
    assert invalid, "esperava ao menos uma conexão inválida"
    assert any(i.code == "invalid_connection" for i in report.issues)


def test_inspect_structure_workbook_sem_issues_retorna_lista_vazia(
    tmp_path: Path,
) -> None:
    xml = _workbook_xml(
        columns=_COLUMNS_BASIC + _COLUMN_CALC_OK,
        worksheets=_WORKSHEET_WITH_LOGIC,
        dashboards=_DASHBOARD,
    )
    report = inspect_structure(_write_twb(tmp_path, xml))

    assert report.issues == []


def test_inspect_structure_twbx_compactado_e_twb_puro_produzem_mesma_estrutura(
    tmp_path: Path,
) -> None:
    xml = _workbook_xml(
        columns=_COLUMNS_BASIC + _COLUMN_CALC_OK + _COLUMN_CALC_BROKEN,
        worksheets=_WORKSHEET_WITH_LOGIC + _WORKSHEET_NO_LOGIC,
        dashboards=_DASHBOARD,
    )
    twb = _write_twb(tmp_path, xml)
    twbx = _write_twbx(tmp_path, xml)

    report_twb = inspect_structure(twb)
    report_twbx = inspect_structure(twbx)

    assert report_twb.model_dump() == report_twbx.model_dump()


def test_inspect_structure_arquivo_xml_corrompido_levanta_erro_tratavel(
    tmp_path: Path,
) -> None:
    corrupt = tmp_path / "broken.twb"
    corrupt.write_text("<workbook version='18.1'><not closed", encoding="utf-8")

    with pytest.raises(StructureParseError):
        inspect_structure(corrupt)


def test_inspect_structure_extensao_invalida_levanta_erro_tratavel(
    tmp_path: Path,
) -> None:
    other = tmp_path / "arquivo.txt"
    other.write_text("irrelevante", encoding="utf-8")

    with pytest.raises(StructureParseError):
        inspect_structure(other)


def test_inspect_structure_workbook_id_padrao_vazio_e_sobrescrevivel(
    tmp_path: Path,
) -> None:
    xml = _workbook_xml(
        columns=_COLUMNS_BASIC,
        worksheets=_WORKSHEET_WITH_LOGIC,
        dashboards=_DASHBOARD,
    )
    twb = _write_twb(tmp_path, xml)

    assert inspect_structure(twb).workbook_id == ""
    assert inspect_structure(twb, workbook_id="luid-123").workbook_id == "luid-123"

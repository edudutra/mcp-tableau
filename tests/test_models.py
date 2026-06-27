"""Testes unitários dos contratos Pydantic em `mcp_tableau.models`."""

import pytest
from pydantic import ValidationError

from mcp_tableau.models import (
    ConnectionInfo,
    DictionaryField,
    ErrorCode,
    FieldInfo,
    FilterInfo,
    PublishResult,
    SheetRef,
    StructureReport,
    ToolError,
)


def test_toolerror_serializa_com_code_e_message() -> None:
    erro = ToolError.of(
        ErrorCode.OVERWRITE_NOT_ALLOWED,
        "Já existe 'vendas'. Reenvie com overwrite=true.",
    )

    dump = erro.model_dump(mode="json")

    assert dump["status"] == "error"
    assert dump["error"]["code"] == "OVERWRITE_NOT_ALLOWED"
    assert dump["error"]["message"].startswith("Já existe")


def test_publishresult_serializa_campos_obrigatorios() -> None:
    resultado = PublishResult(
        content_id="3f9a1c2e",
        content_type="workbook",
        name="Vendas Regionais 2026",
        project_id="a1b2c3d4",
        project_name="Financeiro/Produção",
        mode="overwrite",
        chunked=True,
    )

    dump = resultado.model_dump(mode="json")

    assert dump["status"] == "success"
    assert dump["content_id"] == "3f9a1c2e"
    assert dump["content_type"] == "workbook"
    assert dump["mode"] == "overwrite"
    assert dump["chunked"] is True
    # Campo opcional ausente normaliza para null.
    assert dump["webpage_url"] is None


def test_models_campos_opcionais_aceitam_null() -> None:
    field = FieldInfo(
        name="Receita",
        datatype="real",
        role="measure",
        is_calculated=False,
    )
    dictionary_field = DictionaryField(
        name="Cliente",
        datatype="string",
        is_calculated=False,
    )

    field_dump = field.model_dump(mode="json")
    dict_dump = dictionary_field.model_dump(mode="json")

    assert field_dump["formula"] is None
    assert field_dump["is_broken"] is False
    assert dict_dump["formula"] is None
    assert dict_dump["description"] is None


def test_sheetref_aceita_id_none_preserva_name() -> None:
    sheet = SheetRef(id=None, name="X")

    dump = sheet.model_dump(mode="json")

    # `id` ausente é representado como null (campo presente, não omitido).
    assert dump["id"] is None
    assert dump["name"] == "X"


def test_sheetref_serializa_id_luid() -> None:
    sheet = SheetRef(id="luid", name="X")

    dump = sheet.model_dump(mode="json")

    assert dump["id"] == "luid"
    assert dump["name"] == "X"


def test_structure_report_worksheets_aceita_list_sheetref() -> None:
    report = StructureReport(
        workbook_id="w",
        worksheets=[SheetRef(id="luid-ws", name="Vendas")],
        dashboards=[SheetRef(id=None, name="Painel")],
    )

    dump = report.model_dump(mode="json")

    assert dump["worksheets"] == [{"id": "luid-ws", "name": "Vendas"}]
    assert dump["dashboards"] == [{"id": None, "name": "Painel"}]


def test_structure_report_rejeita_list_str_em_worksheets() -> None:
    with pytest.raises(ValidationError):
        StructureReport(workbook_id="w", worksheets=["A"])


def test_filter_info_worksheet_id_default_none() -> None:
    filtro = FilterInfo(
        worksheet="Vendas por Região",
        field="Região",
        kind="categorical",
        has_logic=True,
    )

    dump = filtro.model_dump(mode="json")

    assert dump["worksheet_id"] is None


def test_filter_info_aceita_worksheet_id() -> None:
    filtro = FilterInfo(
        worksheet="Vendas por Região",
        worksheet_id="luid",
        field="Região",
        kind="categorical",
        has_logic=True,
    )

    dump = filtro.model_dump(mode="json")

    assert dump["worksheet_id"] == "luid"


def test_connection_info_inalterada() -> None:
    # `ConnectionInfo` não recebe `id` nesta feature (RF5 fora do ciclo).
    assert "id" not in ConnectionInfo.model_fields

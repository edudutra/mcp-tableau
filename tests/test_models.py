"""Testes unitários dos contratos Pydantic em `mcp_tableau.models`."""

import pytest
from pydantic import ValidationError

from mcp_tableau.models import (
    ConnectionInfo,
    DictionaryField,
    ErrorCode,
    ExceededDimension,
    FieldInfo,
    FilterInfo,
    HyperColumn,
    HyperCreateResult,
    HyperQueryResult,
    HyperTableInfo,
    InlineColumn,
    PublishResult,
    SheetRef,
    StructureReport,
    ToolError,
    VolumeAlert,
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


# Capacidade 5 — Hyper Datasources ----------------------------------------------


def test_hyper_create_result_serializa_status_success() -> None:
    resultado = HyperCreateResult(
        hyper_path="/data/extratos/vendas_2026.hyper",
        table_name="Extract",
        columns=[HyperColumn(name="valor", type="double", nullable=True)],
        row_count=184230,
        source="csv",
    )

    dump = resultado.model_dump(mode="json")

    assert dump["status"] == "success"
    assert dump["source"] == "csv"
    assert dump["row_count"] == 184230
    # Warnings default para lista vazia (campo presente, não omitido).
    assert dump["warnings"] == []


def test_volume_alert_serializa_status_volume_alert_e_dimensoes() -> None:
    alerta = VolumeAlert(
        exceeded=[
            ExceededDimension(
                dimension="source_file_mb",
                limit=500,
                actual=2048.7,
                risk="Arquivo grande pode esgotar disco.",
            )
        ],
        message="O arquivo tem 2048.7 MB, acima do limiar de 500 MB.",
        how_to_proceed="Repita com confirm_large_operation=true.",
    )

    dump = alerta.model_dump(mode="json")

    assert dump["status"] == "volume_alert"
    assert dump["exceeded"][0]["dimension"] == "source_file_mb"
    assert dump["exceeded"][0]["actual"] == 2048.7
    assert dump["exceeded"][0]["limit"] == 500.0


def test_hyper_query_result_row_count_e_truncated_consistentes() -> None:
    resultado = HyperQueryResult(
        columns=[HyperColumn(name="total", type="double", nullable=True)],
        rows=[[1250341.55], [987222.10]],
        row_count=2,
        truncated=False,
        max_rows=200,
    )

    dump = resultado.model_dump(mode="json")

    assert dump["row_count"] == 2
    assert dump["truncated"] is False
    assert dump["max_rows"] == 200


def test_inline_column_tipo_desconhecido_rejeitado_na_validacao() -> None:
    # Tipo fora do contrato é rejeitado na validação.
    with pytest.raises(ValidationError):
        InlineColumn(name="x", type="varchar")

    # Tipos do contrato (incluindo numeric(p,s)) são aceitos.
    assert InlineColumn(name="a", type="numeric(18,2)").type == "numeric(18,2)"
    assert InlineColumn(name="b", type="big_int").nullable is True


def test_error_code_contem_novos_codigos_hyper_e_db() -> None:
    esperados = (
        "HYPER_INVALID_FILE",
        "HYPER_SCHEMA_MISMATCH",
        "HYPER_SQL_ERROR",
        "DB_CONNECTION_NOT_CONFIGURED",
        "DB_CONNECTION_FAILED",
        "DB_AUTH_FAILED",
        "DB_QUERY_ERROR",
    )
    for codigo in esperados:
        assert codigo in ErrorCode.__members__
        assert ErrorCode[codigo].value == codigo


def test_hyper_table_info_row_count_nulo_permitido() -> None:
    info = HyperTableInfo(
        schema_name="Extract",
        table_name="Extract",
        columns=[HyperColumn(name="v", type="date", nullable=True)],
        row_count=None,
    )

    dump = info.model_dump(mode="json")

    # Contagem não determinável é normalizada para null (campo presente).
    assert dump["row_count"] is None

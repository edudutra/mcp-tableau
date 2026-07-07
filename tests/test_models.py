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
    RenderImageResult,
    RenderPdfResult,
    SheetRef,
    StructureReport,
    ToolError,
    VisualDiagnostic,
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


# Capacidade 2 — Visual (file-save metadata) ------------------------------------


def _make_diagnostic() -> VisualDiagnostic:
    """Helper: cria VisualDiagnostic padrão para testes de RenderImageResult."""
    return VisualDiagnostic(
        is_likely_blank=False,
        blank_ratio=0.02,
        severity="ok",
        message="Imagem ok.",
    )


class TestRenderImageResultFileSaveFields:
    """Testes dos novos campos opcionais de file-save em RenderImageResult."""

    def test_backward_compat_sem_novos_campos(self) -> None:
        """Instanciação sem novos campos funciona (backward compat)."""
        result = RenderImageResult(
            view_id="abc-123",
            diagnostic=_make_diagnostic(),
        )

        dump = result.model_dump(mode="json")

        assert dump["status"] == "success"
        assert dump["view_id"] == "abc-123"
        assert dump["output_path"] is None
        assert dump["file_size_bytes"] is None
        assert dump["save_error"] is None

    def test_com_file_metadata_preenchida(self) -> None:
        """Instanciação com todos os campos de file-save populados."""
        result = RenderImageResult(
            view_id="view-42",
            diagnostic=_make_diagnostic(),
            output_path="/tmp/render.png",
            file_size_bytes=204800,
            save_error=None,
        )

        dump = result.model_dump(mode="json")

        assert dump["output_path"] == "/tmp/render.png"
        assert dump["file_size_bytes"] == 204800
        assert dump["save_error"] is None

    def test_com_save_error(self) -> None:
        """save_error é preenchido quando o save falha."""
        result = RenderImageResult(
            view_id="view-42",
            diagnostic=_make_diagnostic(),
            output_path=None,
            file_size_bytes=None,
            save_error="Permission denied: /root/out.png",
        )

        dump = result.model_dump(mode="json")

        assert dump["save_error"] == "Permission denied: /root/out.png"
        assert dump["output_path"] is None
        assert dump["file_size_bytes"] is None

    def test_serializacao_inclui_campos_none(self) -> None:
        """Campos None aparecem como null na serialização (não omitidos)."""
        result = RenderImageResult(
            view_id="v1",
            diagnostic=_make_diagnostic(),
        )

        dump = result.model_dump(mode="json")

        # Campos estão presentes no dict (não omitidos), com valor null.
        assert "output_path" in dump
        assert "file_size_bytes" in dump
        assert "save_error" in dump


class TestRenderPdfResult:
    """Testes do novo modelo RenderPdfResult."""

    def test_instanciacao_campos_obrigatorios_somente(self) -> None:
        """Instanciação com apenas campos obrigatórios (defaults aplicados)."""
        result = RenderPdfResult(
            view_id="pdf-view-1",
            page_type="A4",
        )

        dump = result.model_dump(mode="json")

        assert dump["status"] == "success"
        assert dump["view_id"] == "pdf-view-1"
        assert dump["page_type"] == "A4"
        assert dump["mime_type"] == "application/pdf"
        assert dump["output_path"] is None
        assert dump["file_size_bytes"] is None
        assert dump["save_error"] is None

    def test_instanciacao_com_todos_os_campos(self) -> None:
        """Instanciação com todos os campos populados."""
        result = RenderPdfResult(
            view_id="pdf-view-2",
            page_type="Letter",
            mime_type="application/pdf",
            output_path="/data/reports/q2.pdf",
            file_size_bytes=1048576,
            save_error=None,
        )

        dump = result.model_dump(mode="json")

        assert dump["view_id"] == "pdf-view-2"
        assert dump["page_type"] == "Letter"
        assert dump["mime_type"] == "application/pdf"
        assert dump["output_path"] == "/data/reports/q2.pdf"
        assert dump["file_size_bytes"] == 1048576
        assert dump["save_error"] is None

    def test_serializacao_estrutura_esperada(self) -> None:
        """Serialização produz exatamente a estrutura JSON esperada."""
        result = RenderPdfResult(
            view_id="v",
            page_type="A4",
            output_path="/out.pdf",
            file_size_bytes=512,
        )

        dump = result.model_dump(mode="json")

        expected_keys = {
            "status",
            "view_id",
            "page_type",
            "mime_type",
            "output_path",
            "file_size_bytes",
            "save_error",
        }
        assert set(dump.keys()) == expected_keys

    def test_status_sempre_success(self) -> None:
        """O campo status é sempre 'success' (Literal constraint)."""
        result = RenderPdfResult(view_id="x", page_type="A3")

        assert result.status == "success"

    def test_status_literal_rejeita_outros_valores(self) -> None:
        """Literal['success'] rejeita outros valores de status."""
        with pytest.raises(ValidationError):
            RenderPdfResult(view_id="x", page_type="A4", status="error")

    def test_com_save_error_preenchido(self) -> None:
        """save_error é string quando o salvamento falha."""
        result = RenderPdfResult(
            view_id="v",
            page_type="A4",
            save_error="Disk full",
        )

        dump = result.model_dump(mode="json")

        assert dump["save_error"] == "Disk full"
        assert dump["output_path"] is None
        assert dump["file_size_bytes"] is None

    def test_mime_type_default_application_pdf(self) -> None:
        """mime_type default é 'application/pdf'."""
        result = RenderPdfResult(view_id="v", page_type="A4")

        assert result.mime_type == "application/pdf"


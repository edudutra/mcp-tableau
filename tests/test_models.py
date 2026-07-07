"""Testes unitários dos contratos Pydantic em `mcp_tableau.models`."""

import pytest
from pydantic import ValidationError

from mcp_tableau.models import (
    CapabilityRule,
    ConnectionInfo,
    DefaultPermissionsResult,
    DictionaryField,
    EffectiveCapability,
    EffectivePermissionsResult,
    ErrorCode,
    ExceededDimension,
    FieldInfo,
    FilterInfo,
    GranteePermissions,
    GroupInfo,
    GroupListResult,
    GroupMembersResult,
    HyperColumn,
    HyperCreateResult,
    HyperQueryResult,
    HyperTableInfo,
    InlineColumn,
    PermContentType,
    PermissionsResult,
    PublishResult,
    ResolveResult,
    SheetRef,
    StructureReport,
    ToolError,
    UserInfo,
    UserListResult,
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


# Capacidade 6 — Permissions ---------------------------------------------------


def test_perm_content_type_tem_seis_membros_lowercase() -> None:
    membros = list(PermContentType)

    assert len(membros) == 6
    esperados = {
        "project",
        "workbook",
        "datasource",
        "view",
        "flow",
        "virtual_connection",
    }
    assert {m.value for m in membros} == esperados
    # StrEnum: o valor coincide com a string e é minúsculo.
    for membro in membros:
        assert isinstance(membro, str)
        assert membro.value == membro.value.lower()


def test_permissions_result_serializa_grantee_e_capability_aninhados() -> None:
    resultado = PermissionsResult(
        content_type="workbook",
        content_id="wb-luid",
        content_name="Vendas Regionais",
        permissions=[
            GranteePermissions(
                grantee_type="group",
                grantee_id="grp-luid",
                grantee_name="Analistas",
                capabilities=[
                    CapabilityRule(name="Read", mode="Allow"),
                    CapabilityRule(name="Write", mode="Deny"),
                ],
            )
        ],
    )

    dump = resultado.model_dump(mode="json")

    assert dump["status"] == "success"
    assert dump["content_type"] == "workbook"
    grantee = dump["permissions"][0]
    assert grantee["grantee_type"] == "group"
    assert grantee["grantee_name"] == "Analistas"
    assert grantee["capabilities"] == [
        {"name": "Read", "mode": "Allow"},
        {"name": "Write", "mode": "Deny"},
    ]


def test_default_permissions_result_valida_for_content_type() -> None:
    resultado = DefaultPermissionsResult(
        project_id="prj-luid",
        project_name="Financeiro",
        for_content_type="workbook",
        permissions=[],
    )

    dump = resultado.model_dump(mode="json")

    assert dump["status"] == "success"
    assert dump["for_content_type"] == "workbook"
    # Lista vazia é estado válido (projeto sem padrões explícitos).
    assert dump["permissions"] == []


def test_user_list_result_lista_vazia_e_total_zero_valido() -> None:
    resultado = UserListResult(users=[], total_count=0)

    dump = resultado.model_dump(mode="json")

    assert dump["status"] == "success"
    assert dump["users"] == []
    assert dump["total_count"] == 0


def test_group_list_e_members_serializam_usuarios() -> None:
    usuario = UserInfo(id="u1", name="jsmith", site_role="Viewer")
    grupos = GroupListResult(
        groups=[GroupInfo(id="g1", name="Analistas", user_count=3)],
        total_count=1,
    )
    membros = GroupMembersResult(
        group_id="g1",
        group_name="Analistas",
        members=[usuario],
    )

    grupos_dump = grupos.model_dump(mode="json")
    membros_dump = membros.model_dump(mode="json")

    assert grupos_dump["groups"][0]["user_count"] == 3
    assert membros_dump["members"][0]["name"] == "jsmith"
    # `last_login` ausente normaliza para null (campo presente).
    assert membros_dump["members"][0]["last_login"] is None


def test_resolve_result_site_role_none_para_grupo_valido() -> None:
    # Resolução de grupo não tem site role.
    resolucao = ResolveResult(id="g1", name="Analistas")

    dump = resolucao.model_dump(mode="json")

    assert dump["status"] == "success"
    assert dump["site_role"] is None


def test_resolve_result_usuario_com_site_role() -> None:
    resolucao = ResolveResult(id="u1", name="jsmith", site_role="Creator")

    dump = resolucao.model_dump(mode="json")

    assert dump["site_role"] == "Creator"


def test_effective_permissions_result_serializa_todos_os_campos() -> None:
    resultado = EffectivePermissionsResult(
        content_type="workbook",
        content_id="wb-luid",
        user_id="u1",
        user_name="jsmith",
        site_role="Viewer",
        is_owner=False,
        is_admin=False,
        capabilities=[
            EffectiveCapability(name="Read", mode="Allow", reason="group_rule"),
            EffectiveCapability(name="Write", mode="Deny", reason="site_role_cap"),
        ],
        summary="Acesso nível Viewer (Read, Filter, ExportImage).",
    )

    dump = resultado.model_dump(mode="json")

    assert dump["status"] == "success"
    assert dump["is_owner"] is False
    assert dump["is_admin"] is False
    assert dump["capabilities"][0] == {
        "name": "Read",
        "mode": "Allow",
        "reason": "group_rule",
    }
    assert dump["capabilities"][1]["reason"] == "site_role_cap"
    assert dump["summary"].startswith("Acesso nível Viewer")


def test_effective_capability_rejeita_mode_invalido() -> None:
    # Apenas "Allow"/"Deny" são aceitos no modo efetivo.
    with pytest.raises(ValidationError):
        EffectiveCapability(name="Read", mode="Unspecified", reason="group_rule")

    assert EffectiveCapability(name="Read", mode="Allow", reason="user_rule").mode == (
        "Allow"
    )


def test_error_code_contem_novos_codigos_permissions() -> None:
    esperados = ("LOCKED_PROJECT", "SHOW_TABS_ENABLED")
    for codigo in esperados:
        assert codigo in ErrorCode.__members__
        assert ErrorCode[codigo].value == codigo
    # Acessível como atributo (contrato usado pelas ferramentas de permissão).
    assert ErrorCode.LOCKED_PROJECT == "LOCKED_PROJECT"

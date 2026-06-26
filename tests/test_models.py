"""Testes unitários dos contratos Pydantic em `mcp_tableau.models`."""

from mcp_tableau.models import (
    DictionaryField,
    ErrorCode,
    FieldInfo,
    PublishResult,
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

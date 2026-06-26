"""Testes unitários das ferramentas MCP de metadados (`tools/metadata.py`).

Todas as dependências de rede são mockadas: `tableau_session` (context manager),
`load_settings`, `MetadataClient` e `client.search_content`. Nenhum teste toca um
Tableau real.
"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock

import pytest

from mcp_tableau.models import (
    ContentRef,
    DataDictionary,
    ErrorCode,
    LineageResult,
    SimilarityResult,
    ToolError,
)
from mcp_tableau.tools import metadata


@pytest.fixture
def fake_client() -> MagicMock:
    """Cliente Tableau fake reutilizado pelas ferramentas."""
    return MagicMock(name="TableauClient")


@pytest.fixture(autouse=True)
def patch_session(monkeypatch: pytest.MonkeyPatch, fake_client: MagicMock) -> MagicMock:
    """Faz `tableau_session` devolver o cliente fake e neutraliza `load_settings`."""

    @contextlib.contextmanager
    def _session(_settings: object):
        yield fake_client

    monkeypatch.setattr(metadata, "tableau_session", _session)
    monkeypatch.setattr(metadata, "load_settings", lambda: object())
    return fake_client


def _patch_metadata_client(
    monkeypatch: pytest.MonkeyPatch, method: str, return_value: object
) -> MagicMock:
    """Substitui `MetadataClient` por um mock cujo `method` devolve `return_value`."""
    instance = MagicMock(name="MetadataClient")
    getattr(instance, method).return_value = return_value
    factory = MagicMock(return_value=instance)
    monkeypatch.setattr(metadata, "MetadataClient", factory)
    return instance


# get_downstream_lineage --------------------------------------------------------


def test_get_downstream_lineage_retorna_dependencias_atribuiveis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_metadata_client(
        monkeypatch,
        "downstream_of_datasource",
        {
            "root": {"id": "ds-1", "name": "Vendas", "type": "datasource"},
            "nodes": [
                {
                    "id": "wb-1",
                    "name": "Painel Vendas",
                    "type": "workbook",
                    "project": "Financeiro",
                    "owner": "ana",
                }
            ],
        },
    )

    result = metadata.get_downstream_lineage("ds-1")

    assert isinstance(result, LineageResult)
    assert result.direction == "downstream"
    assert result.root.id == "ds-1"
    assert len(result.dependencies) == 1
    node = result.dependencies[0]
    assert node.id == "wb-1"
    assert node.name == "Painel Vendas"
    assert node.type == "workbook"
    assert node.project == "Financeiro"
    assert node.owner == "ana"


def test_get_downstream_lineage_sem_dependentes_retorna_lista_vazia_sucesso(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_metadata_client(
        monkeypatch,
        "downstream_of_datasource",
        {
            "root": {"id": "ds-9", "name": "Órfã", "type": "datasource"},
            "nodes": [],
        },
    )

    result = metadata.get_downstream_lineage("ds-9")

    assert isinstance(result, LineageResult)
    assert result.status == "success"
    assert result.dependencies == []


def test_get_downstream_lineage_root_ausente_retorna_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_metadata_client(
        monkeypatch,
        "downstream_of_datasource",
        {"root": None, "nodes": []},
    )

    result = metadata.get_downstream_lineage("inexistente")

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.NOT_FOUND


# get_upstream_lineage ----------------------------------------------------------


def test_get_upstream_lineage_workbook_retorna_fontes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_metadata_client(
        monkeypatch,
        "upstream_of_workbook",
        {
            "root": {"id": "wb-1", "name": "Painel", "type": "workbook"},
            "nodes": [
                {
                    "id": "ds-1",
                    "name": "Fonte Vendas",
                    "type": "datasource",
                    "project": "Dados",
                    "owner": "bruno",
                }
            ],
        },
    )

    result = metadata.get_upstream_lineage("wb-1")

    assert isinstance(result, LineageResult)
    assert result.direction == "upstream"
    assert result.root.id == "wb-1"
    assert result.dependencies[0].id == "ds-1"
    assert result.dependencies[0].type == "datasource"


def test_get_upstream_lineage_content_type_nao_suportado_retorna_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Um datasource não pode ser tratado silenciosamente como workbook: deve ser
    # recusado na validação local, sem instanciar o MetadataClient (sem rede).
    factory = MagicMock(name="MetadataClient", side_effect=AssertionError("sem rede"))
    monkeypatch.setattr(metadata, "MetadataClient", factory)

    result = metadata.get_upstream_lineage("ds-1", content_type="datasource")

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.VALIDATION_ERROR
    factory.assert_not_called()


# get_datasource_dictionary -----------------------------------------------------


def test_get_datasource_dictionary_inclui_formula_de_calculados(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_metadata_client(
        monkeypatch,
        "datasource_dictionary",
        {
            "datasource": {"id": "ds-1", "name": "Vendas", "type": "datasource"},
            "fields": [
                {
                    "name": "Margem",
                    "formula": "[Receita] - [Custo]",
                    "description": "Margem bruta",
                    "is_calculated": True,
                },
                {
                    "name": "Receita",
                    "formula": None,
                    "description": None,
                    "is_calculated": False,
                },
            ],
        },
    )

    result = metadata.get_datasource_dictionary("ds-1")

    assert isinstance(result, DataDictionary)
    assert result.datasource_id == "ds-1"
    assert result.datasource_name == "Vendas"
    calculado = result.fields[0]
    assert calculado.is_calculated is True
    assert calculado.formula == "[Receita] - [Custo]"
    # datatype ausente normalizado para "unknown".
    assert calculado.datatype == "unknown"


def test_get_datasource_dictionary_campos_sem_descricao_normalizados_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_metadata_client(
        monkeypatch,
        "datasource_dictionary",
        {
            "datasource": {"id": "ds-1", "name": "Vendas", "type": "datasource"},
            "fields": [
                {
                    "name": "Receita",
                    "formula": None,
                    "description": None,
                    "is_calculated": False,
                }
            ],
        },
    )

    result = metadata.get_datasource_dictionary("ds-1")

    assert isinstance(result, DataDictionary)
    campo = result.fields[0]
    assert campo.description is None
    assert campo.formula is None
    assert campo.is_calculated is False


def test_get_datasource_dictionary_datasource_ausente_retorna_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_metadata_client(
        monkeypatch,
        "datasource_dictionary",
        {"datasource": None, "fields": []},
    )

    result = metadata.get_datasource_dictionary("inexistente")

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.NOT_FOUND


# search_similar_content --------------------------------------------------------


def test_search_similar_content_retorna_matches_ordenados(
    fake_client: MagicMock,
) -> None:
    fake_client.search_content.return_value = [
        ContentRef(id="wb-1", name="Painel Vendas", type="workbook"),
        ContentRef(id="wb-2", name="Painel de Vendas Mensal", type="workbook"),
        ContentRef(id="ds-1", name="Outra Coisa", type="datasource"),
    ]

    result = metadata.search_similar_content("Painel Vendas")

    assert isinstance(result, SimilarityResult)
    assert result.query == "Painel Vendas"
    assert len(result.matches) >= 1
    scores = [match.score for match in result.matches]
    assert scores == sorted(scores, reverse=True)
    assert result.matches[0].id == "wb-1"


def test_search_similar_content_filtra_por_content_type(
    fake_client: MagicMock,
) -> None:
    fake_client.search_content.return_value = [
        ContentRef(id="wb-1", name="Vendas", type="workbook"),
        ContentRef(id="ds-1", name="Vendas", type="datasource"),
    ]

    result = metadata.search_similar_content("Vendas", content_type="datasource")

    assert isinstance(result, SimilarityResult)
    assert all(match.type == "datasource" for match in result.matches)
    assert {match.id for match in result.matches} == {"ds-1"}


def test_search_similar_content_sem_match_retorna_lista_vazia(
    fake_client: MagicMock,
) -> None:
    fake_client.search_content.return_value = []

    result = metadata.search_similar_content("qualquer")

    assert isinstance(result, SimilarityResult)
    assert result.status == "success"
    assert result.matches == []


@pytest.mark.parametrize("limit", [0, -1, 51, 100])
def test_search_similar_content_limit_invalido_retorna_validation_error(
    fake_client: MagicMock, limit: int
) -> None:
    result = metadata.search_similar_content("vendas", limit=limit)

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.VALIDATION_ERROR
    # Validação acontece ANTES de qualquer rede.
    fake_client.search_content.assert_not_called()

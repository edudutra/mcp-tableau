"""Testes unitários do `MetadataClient` (Metadata API / GraphQL).

O cliente Tableau e a sessão GraphQL são totalmente mockados — nenhum acesso de
rede real. O ponto de mock é `client.server.metadata.query`, que retorna o dict
JSON da Metadata API.
"""

from unittest.mock import MagicMock

import pytest
from tableauserverclient.server.endpoint.exceptions import GraphQLError
from tableauserverclient.server.exceptions import EndpointUnavailableError

from mcp_tableau.models import ErrorCode
from mcp_tableau.tableau.metadata import MetadataClient, MetadataClientError


def _make_client(query_return=None, query_side_effect=None) -> MagicMock:
    """Constrói um TableauClient fake com `.server.metadata.query` mockado."""
    client = MagicMock()
    query = client.server.metadata.query
    if query_side_effect is not None:
        query.side_effect = query_side_effect
    else:
        query.return_value = query_return
    return client


# 3.1 — linhagem descendente ---------------------------------------------------


def test_metadata_query_monta_graphql_e_parseia_resposta():
    """downstream_of_datasource monta GraphQL e parseia nós atribuíveis."""
    response = {
        "data": {
            "publishedDatasources": [
                {
                    "luid": "ds-1",
                    "name": "Vendas",
                    "downstreamWorkbooks": [
                        {
                            "luid": "wb-1",
                            "name": "Dashboard Vendas",
                            "projectName": "Comercial",
                            "owner": {"username": "ana"},
                        }
                    ],
                }
            ]
        }
    }
    client = _make_client(query_return=response)

    result = MetadataClient(client).downstream_of_datasource("ds-1")

    # Query foi montada com a variável de luid correta.
    args, kwargs = client.server.metadata.query.call_args
    assert "downstreamWorkbooks" in args[0]
    assert kwargs["variables"] == {"luid": "ds-1"}

    assert result["root"] == {"id": "ds-1", "name": "Vendas", "type": "datasource"}
    assert result["nodes"] == [
        {
            "id": "wb-1",
            "name": "Dashboard Vendas",
            "type": "workbook",
            "project": "Comercial",
            "owner": "ana",
        }
    ]


def test_metadata_downstream_sem_dependentes_retorna_nodes_vazio():
    """Fonte sem workbooks dependentes retorna root presente e nodes vazio."""
    response = {
        "data": {
            "publishedDatasources": [
                {"luid": "ds-1", "name": "Vendas", "downstreamWorkbooks": []}
            ]
        }
    }
    client = _make_client(query_return=response)

    result = MetadataClient(client).downstream_of_datasource("ds-1")

    assert result["root"]["id"] == "ds-1"
    assert result["nodes"] == []


# 3.2 — linhagem ascendente ----------------------------------------------------


def test_metadata_upstream_of_workbook_retorna_fontes_atribuiveis():
    """upstream_of_workbook parseia fontes de dados ascendentes do workbook."""
    response = {
        "data": {
            "workbooks": [
                {
                    "luid": "wb-1",
                    "name": "Dashboard Vendas",
                    "upstreamDatasources": [
                        {
                            "luid": "ds-1",
                            "name": "Vendas",
                            "projectName": "Comercial",
                            "owner": {"username": "ana"},
                        },
                        {
                            "luid": "ds-2",
                            "name": "Metas",
                            "projectName": None,
                            "owner": None,
                        },
                    ],
                }
            ]
        }
    }
    client = _make_client(query_return=response)

    result = MetadataClient(client).upstream_of_workbook("wb-1")

    args, kwargs = client.server.metadata.query.call_args
    assert "upstreamDatasources" in args[0]
    assert kwargs["variables"] == {"luid": "wb-1"}

    assert result["root"] == {
        "id": "wb-1",
        "name": "Dashboard Vendas",
        "type": "workbook",
    }
    assert result["nodes"] == [
        {
            "id": "ds-1",
            "name": "Vendas",
            "type": "datasource",
            "project": "Comercial",
            "owner": "ana",
        },
        {
            "id": "ds-2",
            "name": "Metas",
            "type": "datasource",
            "project": None,
            "owner": None,
        },
    ]


# 3.3 — dicionário de fonte de dados -------------------------------------------


def test_metadata_dictionary_inclui_formula_de_calculados():
    """datasource_dictionary marca is_calculated e expõe a fórmula."""
    response = {
        "data": {
            "publishedDatasources": [
                {
                    "luid": "ds-1",
                    "name": "Vendas",
                    "fields": [
                        {
                            "name": "Margem",
                            "description": "Margem líquida",
                            "formula": "[Receita] - [Custo]",
                        }
                    ],
                }
            ]
        }
    }
    client = _make_client(query_return=response)

    result = MetadataClient(client).datasource_dictionary("ds-1")

    assert result["datasource"] == {
        "id": "ds-1",
        "name": "Vendas",
        "type": "datasource",
    }
    assert result["fields"] == [
        {
            "name": "Margem",
            "formula": "[Receita] - [Custo]",
            "description": "Margem líquida",
            "is_calculated": True,
        }
    ]


def test_metadata_dictionary_campos_sem_descricao_normalizados_null():
    """Campos sem formula/description são normalizados para None."""
    response = {
        "data": {
            "publishedDatasources": [
                {
                    "luid": "ds-1",
                    "name": "Vendas",
                    "fields": [{"name": "Receita"}],
                }
            ]
        }
    }
    client = _make_client(query_return=response)

    result = MetadataClient(client).datasource_dictionary("ds-1")

    assert result["fields"] == [
        {
            "name": "Receita",
            "formula": None,
            "description": None,
            "is_calculated": False,
        }
    ]


# 3.4 — tradução de erro para UPSTREAM_ERROR -----------------------------------


def test_metadata_erro_graphql_vira_upstream_error():
    """Campo `errors` na resposta vira MetadataClientError(UPSTREAM_ERROR)."""
    response = {"errors": [{"message": "Field 'foo' doesn't exist"}], "data": None}
    client = _make_client(query_return=response)

    with pytest.raises(MetadataClientError) as exc_info:
        MetadataClient(client).downstream_of_datasource("ds-1")

    assert exc_info.value.code is ErrorCode.UPSTREAM_ERROR
    assert "Metadata API" in exc_info.value.message


def test_metadata_endpoint_indisponivel_vira_upstream_error():
    """EndpointUnavailableError é mapeado para UPSTREAM_ERROR acionável."""
    client = _make_client(
        query_side_effect=EndpointUnavailableError("metadata API disabled")
    )

    with pytest.raises(MetadataClientError) as exc_info:
        MetadataClient(client).upstream_of_workbook("wb-1")

    assert exc_info.value.code is ErrorCode.UPSTREAM_ERROR
    assert "indisponível" in exc_info.value.message


def test_metadata_graphql_error_excecao_vira_upstream_error():
    """GraphQLError levantado pelo TSC também vira UPSTREAM_ERROR."""
    client = _make_client(query_side_effect=GraphQLError("boom"))

    with pytest.raises(MetadataClientError) as exc_info:
        MetadataClient(client).datasource_dictionary("ds-1")

    assert exc_info.value.code is ErrorCode.UPSTREAM_ERROR


def test_metadata_erro_nao_vaza_credenciais():
    """A mensagem de erro nunca expõe o segredo do PAT."""
    response = {"errors": [{"message": "denied"}]}
    client = _make_client(query_return=response)

    with pytest.raises(MetadataClientError) as exc_info:
        MetadataClient(client).downstream_of_datasource("ds-1")

    assert "s3cr3t" not in exc_info.value.message


def test_metadata_resposta_sem_data_vira_upstream_error():
    """Resposta sem campo `data` (e sem `errors`) é tratada como upstream error."""
    client = _make_client(query_return={"foo": "bar"})

    with pytest.raises(MetadataClientError) as exc_info:
        MetadataClient(client).datasource_dictionary("ds-1")

    assert exc_info.value.code is ErrorCode.UPSTREAM_ERROR


def test_metadata_luid_inexistente_retorna_root_none():
    """LUID inexistente (lista vazia) retorna root None e nodes vazio."""
    client = _make_client(query_return={"data": {"publishedDatasources": []}})

    result = MetadataClient(client).downstream_of_datasource("nao-existe")

    assert result["root"] is None
    assert result["nodes"] == []

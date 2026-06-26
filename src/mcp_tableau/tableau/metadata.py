"""Cliente da Tableau Metadata API (GraphQL) para linhagem e dicionário.

`MetadataClient` reaproveita a sessão autenticada do `TableauClient` (Tarefa 2.0)
para executar queries GraphQL na Metadata API. Cobre linhagem descendente
(`downstreamWorkbooks`), linhagem ascendente (`upstreamDatasources`) e o
dicionário de campos de uma fonte de dados (`fields { name formula description }`).

As funções retornam **dados parseados** (dicts/listas simples); a montagem dos
modelos Pydantic finais (`LineageResult`/`DataDictionary`) acontece nas tools
(Tarefa 6.0). Erros GraphQL e endpoints indisponíveis viram `MetadataClientError`
com `ErrorCode.UPSTREAM_ERROR`, sem jamais vazar credenciais nas mensagens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from tableauserverclient.server.endpoint.exceptions import GraphQLError
from tableauserverclient.server.exceptions import EndpointUnavailableError

from mcp_tableau.models import ErrorCode

if TYPE_CHECKING:  # pragma: no cover - apenas para type checking
    from tableauserverclient import Server


@runtime_checkable
class _TableauClientLike(Protocol):
    """Protocolo mínimo esperado do `TableauClient` (injeção de dependência).

    Evita acoplamento em runtime ao `tableau/client.py` (escrito em paralelo):
    basta expor o `Server` autenticado do `tableauserverclient` em `.server`.
    """

    server: Server


class MetadataClientError(Exception):
    """Erro acionável da Metadata API, já mapeado para um `ErrorCode`.

    Carrega o `code` (sempre `UPSTREAM_ERROR` nesta camada) e uma `message`
    sanitizada — nunca inclua tokens, PATs ou URLs com credenciais.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# Queries GraphQL --------------------------------------------------------------

_DOWNSTREAM_WORKBOOKS_QUERY = """
query downstreamOfDatasource($luid: String!) {
  publishedDatasources(filter: {luid: $luid}) {
    luid
    name
    downstreamWorkbooks {
      luid
      name
      projectName
      owner {
        username
      }
    }
  }
}
"""

_UPSTREAM_DATASOURCES_QUERY = """
query upstreamOfWorkbook($luid: String!) {
  workbooks(filter: {luid: $luid}) {
    luid
    name
    upstreamDatasources {
      luid
      name
      projectName
      owner {
        username
      }
    }
  }
}
"""

_DATASOURCE_DICTIONARY_QUERY = """
query datasourceDictionary($luid: String!) {
  publishedDatasources(filter: {luid: $luid}) {
    luid
    name
    fields {
      name
      description
      ... on CalculatedField {
        formula
      }
    }
  }
}
"""


class MetadataClient:
    """Executa GraphQL na Metadata API reaproveitando a sessão do `TableauClient`."""

    def __init__(self, client: _TableauClientLike) -> None:
        """Recebe o `TableauClient` (ou objeto com `.server` autenticado) por injeção.

        Não cria sessão própria: usa o `Server` já autenticado do TSC exposto pelo
        cliente, garantindo a mesma credencial/sessão da REST API.
        """
        self._client = client

    # API pública --------------------------------------------------------------

    def downstream_of_datasource(self, datasource_luid: str) -> dict[str, Any]:
        """Linhagem descendente: workbooks que dependem da fonte de dados.

        Retorna `{"root": {...} | None, "nodes": [{id, name, type, project, owner}]}`.
        `nodes` vazio (com `root` presente) significa fonte sem dependentes.
        """
        data = self._execute(_DOWNSTREAM_WORKBOOKS_QUERY, {"luid": datasource_luid})
        root_node = _first(data.get("publishedDatasources"))
        nodes = [
            _parse_lineage_node(wb, "workbook")
            for wb in _as_list(
                root_node.get("downstreamWorkbooks") if root_node else None
            )
        ]
        return {"root": _parse_content_ref(root_node, "datasource"), "nodes": nodes}

    def upstream_of_workbook(self, workbook_luid: str) -> dict[str, Any]:
        """Linhagem ascendente: fontes de dados das quais o workbook depende.

        Retorna `{"root": {...} | None, "nodes": [{id, name, type, project, owner}]}`.
        """
        data = self._execute(_UPSTREAM_DATASOURCES_QUERY, {"luid": workbook_luid})
        root_node = _first(data.get("workbooks"))
        nodes = [
            _parse_lineage_node(ds, "datasource")
            for ds in _as_list(
                root_node.get("upstreamDatasources") if root_node else None
            )
        ]
        return {"root": _parse_content_ref(root_node, "workbook"), "nodes": nodes}

    def datasource_dictionary(self, datasource_luid: str) -> dict[str, Any]:
        """Dicionário de campos da fonte de dados (nome, fórmula, descrição).

        `formula` é `None` para campos não calculados; `description` é `None`
        quando ausente no upstream (degradação Cloud vs Server, RF24).
        Retorna `{"datasource": {...} | None, "fields": [...]}`.
        """
        data = self._execute(_DATASOURCE_DICTIONARY_QUERY, {"luid": datasource_luid})
        root_node = _first(data.get("publishedDatasources"))
        fields = [
            _parse_dictionary_field(field)
            for field in _as_list(root_node.get("fields") if root_node else None)
        ]
        return {
            "datasource": _parse_content_ref(root_node, "datasource"),
            "fields": fields,
        }

    # Execução / tradução de erro ----------------------------------------------

    def _execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Executa um POST GraphQL único e devolve `data`, mapeando erros.

        Erros GraphQL (campo `errors`) e `EndpointUnavailableError` viram
        `MetadataClientError(UPSTREAM_ERROR, ...)`. Nunca inclui credenciais.
        """
        try:
            result = self._client.server.metadata.query(query, variables=variables)
        except EndpointUnavailableError as exc:
            raise MetadataClientError(
                ErrorCode.UPSTREAM_ERROR,
                "Metadata API indisponível neste Tableau (verifique se a Metadata "
                "API está habilitada no servidor/site).",
            ) from exc
        except GraphQLError as exc:
            raise MetadataClientError(
                ErrorCode.UPSTREAM_ERROR,
                "Falha ao consultar a Metadata API do Tableau (erro GraphQL).",
            ) from exc

        errors = result.get("errors")
        if errors:
            detail = _summarize_errors(errors)
            raise MetadataClientError(
                ErrorCode.UPSTREAM_ERROR,
                f"Falha ao consultar a Metadata API do Tableau: {detail}",
            )

        data = result.get("data")
        if not isinstance(data, dict):
            raise MetadataClientError(
                ErrorCode.UPSTREAM_ERROR,
                "Resposta inesperada da Metadata API do Tableau (sem campo 'data').",
            )
        return data


# Helpers de parsing -----------------------------------------------------------


def _as_list(value: Any) -> list[dict[str, Any]]:
    """Normaliza para lista de dicts; `None`/ausente vira `[]`."""
    if not value:
        return []
    return [item for item in value if isinstance(item, dict)]


def _first(value: Any) -> dict[str, Any] | None:
    """Retorna o primeiro dict da lista (nó-raiz da query) ou `None`."""
    items = _as_list(value)
    return items[0] if items else None


def _parse_content_ref(
    node: dict[str, Any] | None, type_: str
) -> dict[str, Any] | None:
    """Monta a referência atribuível do nó-raiz (id, name, type)."""
    if node is None:
        return None
    return {
        "id": node.get("luid"),
        "name": node.get("name"),
        "type": type_,
    }


def _parse_lineage_node(node: dict[str, Any], type_: str) -> dict[str, Any]:
    """Monta um nó de dependência: id, nome, tipo, projeto e owner (se houver)."""
    owner = node.get("owner")
    owner_name = owner.get("username") if isinstance(owner, dict) else None
    return {
        "id": node.get("luid"),
        "name": node.get("name"),
        "type": type_,
        "project": node.get("projectName"),
        "owner": owner_name,
    }


def _parse_dictionary_field(field: dict[str, Any]) -> dict[str, Any]:
    """Monta um campo do dicionário, normalizando ausentes para `None`.

    `is_calculated` deriva da presença de `formula` na resposta GraphQL
    (fragmento `... on CalculatedField`).
    """
    formula = field.get("formula")
    return {
        "name": field.get("name"),
        "formula": formula,
        "description": field.get("description"),
        "is_calculated": formula is not None,
    }


def _summarize_errors(errors: Any) -> str:
    """Extrai mensagens GraphQL de forma segura (sem expor credenciais)."""
    if not isinstance(errors, list):
        return "erro desconhecido"
    messages = [
        str(err.get("message"))
        for err in errors
        if isinstance(err, dict) and err.get("message")
    ]
    return "; ".join(messages) if messages else "erro desconhecido"

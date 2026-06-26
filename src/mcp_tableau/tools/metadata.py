"""Ferramentas MCP da Capacidade 4 (Dicionário/Contexto): linhagem e busca.

Ferramentas finas que orquestram o `MetadataClient` (Metadata API / GraphQL) e a
validação de similaridade pura (`rank_similar`). Cobrem linhagem descendente de
uma fonte de dados, linhagem ascendente de um conteúdo, dicionário de campos de
uma fonte de dados e busca fuzzy de conteúdo semelhante.

O acesso ao Tableau acontece exclusivamente via `tableau/`; cada ferramenta abre
uma sessão autenticada, delega às camadas de integração/validação e devolve um
modelo Pydantic de sucesso ou o envelope `ToolError`. O registro no servidor
FastMCP é feito por `register(mcp)`, chamado por `server.py`.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_tableau.config import load_settings
from mcp_tableau.models import (
    ContentRef,
    DataDictionary,
    DictionaryField,
    ErrorCode,
    LineageNode,
    LineageResult,
    SimilarityResult,
    ToolError,
)
from mcp_tableau.tableau.client import TableauClientError, tableau_session
from mcp_tableau.tableau.metadata import MetadataClient, MetadataClientError
from mcp_tableau.validation.similarity import rank_similar

# Intervalo aceito para o número máximo de resultados da busca de similaridade.
_LIMIT_MIN = 1
_LIMIT_MAX = 50

# Tipos de conteúdo aceitos como raiz da linhagem ascendente. Apenas workbook é
# suportado no MVP; datasource exige uma query GraphQL distinta (tabelas/bancos
# upstream) ainda não implementada na camada `MetadataClient`.
_UPSTREAM_CONTENT_TYPES = frozenset({"workbook"})


def get_downstream_lineage(datasource_id: str) -> LineageResult | ToolError:
    """Lista os conteúdos que dependem de uma fonte de dados (linhagem descendente).

    Consulta a Metadata API para descobrir os workbooks construídos sobre a fonte
    de dados informada, devolvendo cada dependente de forma atribuível (id, nome,
    tipo, projeto e owner). Uma fonte sem dependentes retorna `dependencies=[]`
    com `status="success"` — ausência de dependentes não é erro.

    Args:
        datasource_id: LUID da fonte de dados raiz.

    Returns:
        `LineageResult` (`direction="downstream"`) em caso de sucesso, ou
        `ToolError` (`NOT_FOUND` se a fonte não existe; `UPSTREAM_ERROR`,
        `AUTH_FAILED`, etc. para falhas de comunicação).
    """
    try:
        with tableau_session(load_settings()) as client:
            data = MetadataClient(client).downstream_of_datasource(datasource_id)
    except (MetadataClientError, TableauClientError) as exc:
        return ToolError.of(exc.code, exc.message)

    if data["root"] is None:
        return ToolError.of(
            ErrorCode.NOT_FOUND,
            f"Fonte de dados '{datasource_id}' não encontrada no Tableau.",
        )

    return LineageResult(
        direction="downstream",
        root=ContentRef(**data["root"]),
        dependencies=[LineageNode(**node) for node in data["nodes"]],
    )


def get_upstream_lineage(
    content_id: str, content_type: str = "workbook"
) -> LineageResult | ToolError:
    """Lista as fontes de dados das quais um conteúdo depende (linhagem ascendente).

    Consulta a Metadata API para descobrir as fontes de dados consumidas pelo
    conteúdo informado, devolvendo cada origem de forma atribuível (id, nome,
    tipo, projeto e owner). Um conteúdo sem fontes ascendentes retorna
    `dependencies=[]` com `status="success"`.

    Args:
        content_id: LUID do conteúdo raiz (workbook).
        content_type: Tipo do conteúdo raiz; apenas `"workbook"` é suportado no
            momento. Outros valores são recusados com `VALIDATION_ERROR`.

    Returns:
        `LineageResult` (`direction="upstream"`) em caso de sucesso, ou
        `ToolError` (`VALIDATION_ERROR` se `content_type` não for suportado;
        `NOT_FOUND` se o conteúdo não existe; `UPSTREAM_ERROR`, `AUTH_FAILED`,
        etc. para falhas de comunicação).
    """
    # Validação local ANTES de qualquer rede: não tratar silenciosamente um
    # datasource como workbook (resultaria em NOT_FOUND/resultado incorreto).
    if content_type not in _UPSTREAM_CONTENT_TYPES:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"content_type '{content_type}' não suportado para linhagem "
            "ascendente; use 'workbook'.",
        )

    try:
        with tableau_session(load_settings()) as client:
            data = MetadataClient(client).upstream_of_workbook(content_id)
    except (MetadataClientError, TableauClientError) as exc:
        return ToolError.of(exc.code, exc.message)

    if data["root"] is None:
        return ToolError.of(
            ErrorCode.NOT_FOUND,
            f"Conteúdo '{content_id}' não encontrado no Tableau.",
        )

    return LineageResult(
        direction="upstream",
        root=ContentRef(**data["root"]),
        dependencies=[LineageNode(**node) for node in data["nodes"]],
    )


def get_datasource_dictionary(datasource_id: str) -> DataDictionary | ToolError:
    """Retorna o dicionário de campos de uma fonte de dados (nome, fórmula, descrição).

    Consulta a Metadata API e devolve cada campo com seu nome, indicação de campo
    calculado e, quando disponíveis, a fórmula e a descrição homologada.
    `formula`/`description` podem ser `null` (campos não calculados ou sem
    descrição no upstream); `datatype` ausente é normalizado para `"unknown"`.

    Args:
        datasource_id: LUID da fonte de dados.

    Returns:
        `DataDictionary` em caso de sucesso, ou `ToolError` (`NOT_FOUND` se a
        fonte não existe; `UPSTREAM_ERROR`, `AUTH_FAILED`, etc.).
    """
    try:
        with tableau_session(load_settings()) as client:
            data = MetadataClient(client).datasource_dictionary(datasource_id)
    except (MetadataClientError, TableauClientError) as exc:
        return ToolError.of(exc.code, exc.message)

    root = data["datasource"]
    if root is None:
        return ToolError.of(
            ErrorCode.NOT_FOUND,
            f"Fonte de dados '{datasource_id}' não encontrada no Tableau.",
        )

    return DataDictionary(
        datasource_id=root["id"],
        datasource_name=root["name"],
        fields=[
            DictionaryField(
                name=field["name"],
                datatype=field.get("datatype") or "unknown",
                is_calculated=field["is_calculated"],
                formula=field.get("formula"),
                description=field.get("description"),
            )
            for field in data["fields"]
        ],
    )


def search_similar_content(
    query: str, content_type: str = "all", limit: int = 10
) -> SimilarityResult | ToolError:
    """Busca conteúdo semelhante por nome para evitar duplicação (busca fuzzy).

    Lista os candidatos via REST e os ranqueia por similaridade ao termo, do maior
    para o menor `score`. Opcionalmente filtra por tipo de conteúdo. Nenhum
    semelhante encontrado retorna `matches=[]` com `status="success"` — ausência
    de similar não é erro.

    Args:
        query: Termo de busca (nome ou parte do nome do conteúdo).
        content_type: Filtra por tipo (`"workbook"`/`"datasource"`); `"all"` não
            filtra.
        limit: Número máximo de resultados (1–50).

    Returns:
        `SimilarityResult` ordenado por `score` em caso de sucesso, ou `ToolError`
        (`VALIDATION_ERROR` se `limit` está fora de 1–50; `UPSTREAM_ERROR`,
        `AUTH_FAILED`, etc. para falhas de comunicação).
    """
    # Validação local ANTES de qualquer rede.
    if not _LIMIT_MIN <= limit <= _LIMIT_MAX:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"limit deve estar entre {_LIMIT_MIN} e {_LIMIT_MAX} (recebido {limit}).",
        )

    try:
        with tableau_session(load_settings()) as client:
            candidates = client.search_content(query)
    except (MetadataClientError, TableauClientError) as exc:
        return ToolError.of(exc.code, exc.message)

    if content_type != "all":
        candidates = [ref for ref in candidates if ref.type == content_type]

    matches = rank_similar(query, candidates, limit)
    return SimilarityResult(query=query, matches=matches)


def register(mcp: FastMCP) -> None:
    """Registra as ferramentas de metadados na instância FastMCP."""
    mcp.tool(get_downstream_lineage)
    mcp.tool(get_upstream_lineage)
    mcp.tool(get_datasource_dictionary)
    mcp.tool(search_similar_content)

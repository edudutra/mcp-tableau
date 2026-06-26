"""Ferramentas MCP da Capacidade 1 (Deploy): publicação/sobrescrita.

Ferramentas finas que validam a entrada localmente (extensão/existência do
arquivo) **antes** de qualquer chamada de rede e delegam a publicação ao
`TableauClient`. Resolvem o projeto de destino por nome, respeitam a indicação
explícita de sobrescrita (RF7) e devolvem `PublishResult` ou o envelope
`ToolError`.

O acesso ao Tableau acontece exclusivamente via `tableau/client.py`; o registro
no servidor FastMCP é feito por `register(mcp)`, chamado por `server.py`.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from mcp_tableau.config import load_settings
from mcp_tableau.models import ContentType, ErrorCode, PublishResult, ToolError
from mcp_tableau.tableau.client import TableauClientError, tableau_session

# Extensões aceitas por tipo de conteúdo publicável.
_WORKBOOK_SUFFIXES = frozenset({".twb", ".twbx"})
_DATASOURCE_SUFFIXES = frozenset({".tds", ".tdsx"})


def publish_workbook(
    file_path: str, project_name: str, overwrite: bool = False
) -> PublishResult | ToolError:
    """Publica um novo workbook ou sobrescreve um existente em um projeto.

    O arquivo deve ser `.twb`/`.twbx` e existir localmente. O projeto de destino
    é resolvido por nome para o LUID antes da publicação. Com `overwrite=false`,
    se já houver workbook de mesmo nome no projeto, a operação é recusada com
    `OVERWRITE_NOT_ALLOWED` (RF7); com `overwrite=true`, é criada uma nova versão.
    Artefatos acima de 64 MB usam chunking transparente (`chunked=true`).

    Args:
        file_path: Caminho local do arquivo `.twb`/`.twbx`.
        project_name: Nome do projeto de destino no Tableau.
        overwrite: Quando `true`, sobrescreve conteúdo existente (nova versão).

    Returns:
        `PublishResult` em caso de sucesso, ou `ToolError` com código acionável
        (`INVALID_FILE`, `PROJECT_NOT_FOUND`, `OVERWRITE_NOT_ALLOWED`,
        `AUTH_FAILED`, `PERMISSION_DENIED`, `PAYLOAD_TOO_LARGE`, `UPSTREAM_ERROR`).
    """
    return _publish("workbook", file_path, project_name, overwrite)


def publish_datasource(
    file_path: str, project_name: str, overwrite: bool = False
) -> PublishResult | ToolError:
    """Publica uma nova fonte de dados ou sobrescreve uma existente em um projeto.

    Análoga a `publish_workbook` para `.tds`/`.tdsx`. Mesmas regras de resolução
    de projeto, sobrescrita explícita (RF7) e chunking transparente.

    Args:
        file_path: Caminho local do arquivo `.tds`/`.tdsx`.
        project_name: Nome do projeto de destino no Tableau.
        overwrite: Quando `true`, sobrescreve conteúdo existente (nova versão).

    Returns:
        `PublishResult` (`content_type="datasource"`) em caso de sucesso, ou
        `ToolError` com código acionável.
    """
    return _publish("datasource", file_path, project_name, overwrite)


def _publish(
    content_type: ContentType,
    file_path: str,
    project_name: str,
    overwrite: bool,
) -> PublishResult | ToolError:
    """Fluxo comum de publicação: valida local, resolve projeto e delega ao client."""
    path = Path(file_path)
    valid_suffixes = (
        _WORKBOOK_SUFFIXES if content_type == "workbook" else _DATASOURCE_SUFFIXES
    )
    expected = " ou ".join(sorted(valid_suffixes))

    # Validação local ANTES de qualquer rede.
    if path.suffix.lower() not in valid_suffixes:
        return ToolError.of(
            ErrorCode.INVALID_FILE,
            f"Extensão '{path.suffix}' inválida para {content_type}. "
            f"Esperado {expected}.",
        )
    if not path.is_file():
        return ToolError.of(
            ErrorCode.INVALID_FILE,
            f"Arquivo não encontrado: '{file_path}'.",
        )

    try:
        with tableau_session(load_settings()) as client:
            project_id = client.find_project_id(project_name)
            if project_id is None:
                return ToolError.of(
                    ErrorCode.PROJECT_NOT_FOUND,
                    f"Projeto '{project_name}' não encontrado no Tableau.",
                )

            candidate_name = path.stem
            if not overwrite and _content_exists(
                client, candidate_name, project_name, content_type
            ):
                return ToolError.of(
                    ErrorCode.OVERWRITE_NOT_ALLOWED,
                    f"Já existe {content_type} '{candidate_name}' no projeto "
                    f"'{project_name}'. Reenvie com overwrite=true para criar "
                    "uma nova versão.",
                )

            if content_type == "workbook":
                ref = client.publish_workbook(path, project_id, overwrite=overwrite)
            else:
                ref = client.publish_datasource(path, project_id, overwrite=overwrite)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    return PublishResult(
        content_id=ref.content_id,
        content_type=ref.content_type,
        name=ref.name,
        project_id=ref.project_id,
        project_name=ref.project_name,
        mode=ref.mode,
        chunked=ref.chunked,
        webpage_url=ref.webpage_url,
    )


def _content_exists(
    client, name: str, project_name: str, content_type: ContentType
) -> bool:
    """Indica se já existe conteúdo de mesmo nome/tipo no projeto de destino.

    A checagem é exata por nome (case-insensitive) e por projeto, restrita ao
    tipo de conteúdo publicado. Usada para recusar sobrescrita implícita (RF7).
    """
    needle = name.casefold()
    project = project_name.casefold()
    for ref in client.search_content(name):
        if (
            ref.type == content_type
            and ref.name.casefold() == needle
            and (ref.project or "").casefold() == project
        ):
            return True
    return False


def register(mcp: FastMCP) -> None:
    """Registra as ferramentas de deploy na instância FastMCP."""
    mcp.tool(publish_workbook)
    mcp.tool(publish_datasource)

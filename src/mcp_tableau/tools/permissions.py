"""Ferramentas MCP da Capacidade 6 (Permissions): resolução de usuários e grupos.

Ferramentas de resolução que permitem ao agente encontrar usuários/grupos por
nome e inspecionar membros de grupo antes de aplicar permissões. Todas delegam
ao `TableauClient` e devolvem modelos Pydantic tipados ou o envelope `ToolError`.

O acesso ao Tableau acontece exclusivamente via `tableau/client.py`; o registro
no servidor FastMCP é feito por `register(mcp)`, chamado por `server.py`.
"""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_tableau.config import load_settings
from mcp_tableau.models import (
    GroupInfo,
    GroupListResult,
    GroupMembersResult,
    ResolveResult,
    ToolError,
    UserInfo,
    UserListResult,
)
from mcp_tableau.tableau.client import TableauClientError, tableau_session

# -- Ferramentas de resolução --------------------------------------------------


def list_users(name_filter: str | None = None) -> UserListResult | ToolError:
    """Lista usuários do site, opcionalmente filtrados por nome.

    Retorna todos os usuários do site com seus IDs, nomes e site roles. Quando
    ``name_filter`` é fornecido, aplica filtro server-side (match exato) para
    reduzir o resultado.

    Args:
        name_filter: Nome exato para filtro server-side. Se ``None``, lista
            todos os usuários do site (paginação completa).

    Returns:
        ``UserListResult`` com a lista de usuários e contagem total, ou
        ``ToolError`` em caso de falha de autenticação/rede.
    """
    try:
        with tableau_session(load_settings()) as client:
            raw_users = client.list_users(name_filter)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    users = [
        UserInfo(id=uid, name=uname, site_role=role) for uid, uname, role in raw_users
    ]
    return UserListResult(users=users, total_count=len(users))


def list_groups(name_filter: str | None = None) -> GroupListResult | ToolError:
    """Lista grupos do site, opcionalmente filtrados por nome.

    Retorna todos os grupos do site com seus IDs, nomes e contagem de membros.
    Quando ``name_filter`` é fornecido, aplica filtro server-side (match exato).

    Args:
        name_filter: Nome exato para filtro server-side. Se ``None``, lista
            todos os grupos do site (paginação completa).

    Returns:
        ``GroupListResult`` com a lista de grupos e contagem total, ou
        ``ToolError`` em caso de falha de autenticação/rede.
    """
    try:
        with tableau_session(load_settings()) as client:
            raw_groups = client.list_groups(name_filter)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    groups = [
        GroupInfo(id=gid, name=gname, user_count=count)
        for gid, gname, count in raw_groups
    ]
    return GroupListResult(groups=groups, total_count=len(groups))


def resolve_user(name: str) -> ResolveResult | ToolError:
    """Resolve um nome de usuário para seu LUID e site role.

    Busca o usuário por nome exato via filtro server-side. Retorna
    ``ToolError(NOT_FOUND)`` se o usuário não existir no site.

    Args:
        name: Nome exato do usuário (site username) a resolver.

    Returns:
        ``ResolveResult`` com id, nome e site_role do usuário, ou
        ``ToolError`` com código ``NOT_FOUND`` ou erro de rede/auth.
    """
    try:
        with tableau_session(load_settings()) as client:
            user_id, site_role = client.resolve_user(name)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    return ResolveResult(id=user_id, name=name, site_role=site_role)


def resolve_group(name: str) -> ResolveResult | ToolError:
    """Resolve um nome de grupo para seu LUID.

    Busca o grupo por nome exato via filtro server-side. Retorna
    ``ToolError(NOT_FOUND)`` se o grupo não existir no site.

    Args:
        name: Nome exato do grupo a resolver.

    Returns:
        ``ResolveResult`` com id e nome do grupo (``site_role=None``), ou
        ``ToolError`` com código ``NOT_FOUND`` ou erro de rede/auth.
    """
    try:
        with tableau_session(load_settings()) as client:
            group_id, _ = client.resolve_group(name)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    return ResolveResult(id=group_id, name=name)


def list_group_members(group_name: str) -> GroupMembersResult | ToolError:
    """Lista os membros de um grupo, resolvendo o grupo por nome.

    Primeiro resolve o nome do grupo para obter seu LUID, depois lista todos os
    membros com paginação completa. Retorna ``ToolError(NOT_FOUND)`` se o grupo
    não existir.

    Args:
        group_name: Nome exato do grupo cujos membros serão listados.

    Returns:
        ``GroupMembersResult`` com id do grupo, nome e lista de membros, ou
        ``ToolError`` com código ``NOT_FOUND`` ou erro de rede/auth.
    """
    try:
        with tableau_session(load_settings()) as client:
            group_id, _ = client.resolve_group(group_name)
            raw_members = client.list_group_members(group_id)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    members = [
        UserInfo(id=uid, name=uname, site_role=role) for uid, uname, role in raw_members
    ]
    return GroupMembersResult(group_id=group_id, group_name=group_name, members=members)


# -- Registro ------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Registra as ferramentas de resolução de usuários/grupos na instância FastMCP."""
    mcp.tool(list_users)
    mcp.tool(list_groups)
    mcp.tool(resolve_user)
    mcp.tool(resolve_group)
    mcp.tool(list_group_members)

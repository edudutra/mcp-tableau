"""Ferramentas MCP da Capacidade 6 (Permissions): resolução e CRUD de permissões.

Ferramentas de resolução que permitem ao agente encontrar usuários/grupos por
nome e inspecionar membros de grupo antes de aplicar permissões. Ferramentas
CRUD (`grant_permissions`, `revoke_permissions`, `list_permissions`) que aplicam,
removem e auditam regras de permissão em qualquer tipo de conteúdo Tableau.

Todas delegam ao `TableauClient` e devolvem modelos Pydantic tipados ou o
envelope `ToolError`. Operações de escrita (grant/revoke) realizam detecção
eager de projeto bloqueado e validação de showTabs antes da mutação.

O acesso ao Tableau acontece exclusivamente via `tableau/client.py`; o registro
no servidor FastMCP é feito por `register(mcp)`, chamado por `server.py`.
"""

from __future__ import annotations

import tableauserverclient as TSC
from fastmcp import FastMCP

from mcp_tableau.config import load_settings
from mcp_tableau.models import (
    CapabilityRule,
    DefaultPermissionsResult,
    EffectiveCapability,
    EffectivePermissionsResult,
    ErrorCode,
    GranteePermissions,
    GroupInfo,
    GroupListResult,
    GroupMembersResult,
    PermContentType,
    PermissionsResult,
    ResolveResult,
    ToolError,
    UserInfo,
    UserListResult,
)
from mcp_tableau.tableau.client import (
    TableauClient,
    TableauClientError,
    tableau_session,
)

# -- Constante de teto de capabilities por site role (ADR-002) -----------------
# Mapeia cada site role ao conjunto MÁXIMO de capabilities permitidas.
# Admins (ServerAdministrator, SiteAdministratorCreator, SiteAdministratorExplorer)
# têm bypass total e não são limitados por este mapa.
# Baseado em: https://help.tableau.com/current/server-linux/en-us/permission_license_siterole.htm

SITE_ROLE_CAPS: dict[str, frozenset[str]] = {
    "Creator": frozenset(
        {
            # Projects
            "View",
            "Publish",
            # Workbooks
            "Read",
            "Filter",
            "ViewComments",
            "AddComment",
            "ExportImage",
            "ExportData",
            "ShareView",
            "ViewUnderlyingData",
            "WebEdit",
            "DownloadWorkbook",
            "Write",
            "CreateRefreshMetrics",
            "Move",
            "Delete",
            "ChangePermissions",
            "RefreshExtracts",
            "ExportXml",
            # Datasources
            "Connect",
            "DownloadDatasource",
            "CreateMetricDefinitions",
            # Flows
            "DownloadFlow",
            "WebEditFlow",
            "RunFlow",
            "Execute",
            # General
            "ChangeHierarchy",
            "RunExplainData",
        }
    ),
    "Explorer (Can Publish)": frozenset(
        {
            # Projects
            "View",
            "Publish",
            # Workbooks
            "Read",
            "Filter",
            "ViewComments",
            "AddComment",
            "ExportImage",
            "ExportData",
            "ShareView",
            "ViewUnderlyingData",
            "WebEdit",
            "DownloadWorkbook",
            "Write",
            "CreateRefreshMetrics",
            "Move",
            "Delete",
            "ChangePermissions",
            "RefreshExtracts",
            "ExportXml",
            # Datasources
            "Connect",
            "DownloadDatasource",
            "CreateMetricDefinitions",
            # Flows
            "DownloadFlow",
            "RunFlow",
            "Execute",
            # General
            "ChangeHierarchy",
            "RunExplainData",
        }
    ),
    "ExplorerCanPublish": frozenset(
        {
            # Alias for TSC site_role value
            "View",
            "Publish",
            "Read",
            "Filter",
            "ViewComments",
            "AddComment",
            "ExportImage",
            "ExportData",
            "ShareView",
            "ViewUnderlyingData",
            "WebEdit",
            "DownloadWorkbook",
            "Write",
            "CreateRefreshMetrics",
            "Move",
            "Delete",
            "ChangePermissions",
            "RefreshExtracts",
            "ExportXml",
            "Connect",
            "DownloadDatasource",
            "CreateMetricDefinitions",
            "DownloadFlow",
            "RunFlow",
            "Execute",
            "ChangeHierarchy",
            "RunExplainData",
        }
    ),
    "Explorer": frozenset(
        {
            # Projects
            "View",
            # Workbooks
            "Read",
            "Filter",
            "ViewComments",
            "AddComment",
            "ExportImage",
            "ExportData",
            "ShareView",
            "ViewUnderlyingData",
            "WebEdit",
            "DownloadWorkbook",
            # Datasources
            "Connect",
            "DownloadDatasource",
            # Flows
            "DownloadFlow",
            # General
            "RunExplainData",
        }
    ),
    "Viewer": frozenset(
        {
            # Projects
            "View",
            # Workbooks
            "Read",
            "Filter",
            "ViewComments",
            "AddComment",
            "ExportImage",
            "ExportData",
            # Datasources
            "Connect",
            # General
            "RunExplainData",
        }
    ),
    "Unlicensed": frozenset(),
    "ReadOnly": frozenset(
        {
            "View",
            "Read",
        }
    ),
}

# Site roles com bypass total (admin).
_ADMIN_SITE_ROLES = frozenset(
    {
        "ServerAdministrator",
        "SiteAdministratorCreator",
        "SiteAdministrator",
        "SiteAdministratorExplorer",
    }
)

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


# -- Helpers internos -----------------------------------------------------------

_VALID_GRANTEE_TYPES = frozenset({"user", "group"})
_VALID_MODES = frozenset({"Allow", "Deny"})


def _validate_content_type(content_type: str) -> PermContentType | ToolError:
    """Valida e converte ``content_type`` string para o enum ``PermContentType``.

    Retorna ``ToolError(VALIDATION_ERROR)`` se o valor não for válido.
    """
    try:
        return PermContentType(content_type)
    except ValueError:
        valid = ", ".join(m.value for m in PermContentType)
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"content_type '{content_type}' inválido. Valores aceitos: {valid}.",
        )


def _validate_grantee_type(grantee_type: str) -> ToolError | None:
    """Valida ``grantee_type`` é 'user' ou 'group'.

    Retorna ``ToolError`` se inválido.
    """
    if grantee_type not in _VALID_GRANTEE_TYPES:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"grantee_type '{grantee_type}' inválido. Use 'user' ou 'group'.",
        )
    return None


def _validate_capabilities(capabilities: dict[str, str]) -> ToolError | None:
    """Valida formato de capabilities dict: {name: mode}.

    Retorna ``ToolError`` se inválido.
    """
    if not capabilities:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            "capabilities não pode ser vazio.",
        )
    for name, mode in capabilities.items():
        if mode not in _VALID_MODES:
            return ToolError.of(
                ErrorCode.VALIDATION_ERROR,
                f"Modo '{mode}' inválido para capability '{name}'. "
                f"Use 'Allow' ou 'Deny'.",
            )
    return None


def _resolve_grantee(
    client: TableauClient, grantee_type: str, grantee_name: str
) -> tuple[str, str | None] | ToolError:
    """Resolve grantee_name para LUID. Retorna (luid, site_role|None) ou ToolError."""
    try:
        if grantee_type == "user":
            user_id, site_role = client.resolve_user(grantee_name)
            return (user_id, site_role)
        else:
            group_id, _ = client.resolve_group(grantee_name)
            return (group_id, None)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)


def _check_locked_project(
    client: TableauClient, content_type: PermContentType, content_id: str
) -> ToolError | None:
    """Detecção eager de projeto bloqueado para operações de escrita.

    Projetos não podem ser bloqueados em relação a si mesmos, então para
    ``content_type == project`` o check é ignorado.

    Retorna ``ToolError(LOCKED_PROJECT)`` se o projeto estiver bloqueado.
    """
    if content_type == PermContentType.project:
        return None

    try:
        project_id = client.get_content_project_id(content_type, content_id)
        lock_state = client.get_project_lock_state(project_id)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    if lock_state.startswith("LockedTo"):
        return ToolError.of(
            ErrorCode.LOCKED_PROJECT,
            f"O projeto está bloqueado (modo: {lock_state}). "
            "Permissões de conteúdo são gerenciadas pelo projeto. "
            "Use 'set_default_permissions' no projeto para alterar as permissões.",
        )
    return None


def _build_permission_rule(
    grantee_type: str,
    grantee_id: str,
    capabilities: dict[str, str],
) -> TSC.PermissionsRule:
    """Constrói um ``TSC.PermissionsRule`` a partir dos parâmetros da tool."""
    grantee = TSC.GroupItem() if grantee_type == "group" else TSC.UserItem()
    grantee._id = grantee_id

    caps: dict[str, str] = {}
    for cap_name, mode in capabilities.items():
        caps[cap_name] = mode

    return TSC.PermissionsRule(
        grantee=grantee,
        capabilities=caps,
    )


def _build_revoke_rule(
    grantee_type: str,
    grantee_id: str,
    capability_name: str,
    mode: str,
) -> TSC.PermissionsRule:
    """Constrói uma regra de revogação com uma única capability."""
    grantee = TSC.GroupItem() if grantee_type == "group" else TSC.UserItem()
    grantee._id = grantee_id

    return TSC.PermissionsRule(
        grantee=grantee,
        capabilities={capability_name: mode},
    )


def _rules_to_permissions_result(
    rules: list[object],
    content_type: PermContentType,
    content_id: str,
    content_name: str,
) -> PermissionsResult:
    """Converte lista de ``TSC.PermissionsRule`` para ``PermissionsResult``."""
    grantee_perms: list[GranteePermissions] = []
    for rule in rules:
        grantee = getattr(rule, "grantee", None)
        grantee_id = getattr(grantee, "id", "") or getattr(grantee, "_id", "")
        grantee_name_val = getattr(grantee, "name", None) or ""

        # Determinar tipo de grantee
        if isinstance(grantee, TSC.GroupItem):
            g_type = "group"
        else:
            g_type = "user"

        caps_dict = getattr(rule, "capabilities", {}) or {}
        caps = [
            CapabilityRule(name=cap_name, mode=cap_mode)
            for cap_name, cap_mode in caps_dict.items()
        ]

        grantee_perms.append(
            GranteePermissions(
                grantee_type=g_type,
                grantee_id=grantee_id,
                grantee_name=grantee_name_val,
                capabilities=caps,
            )
        )

    return PermissionsResult(
        content_type=content_type.value,
        content_id=content_id,
        content_name=content_name,
        permissions=grantee_perms,
    )


# -- Ferramentas CRUD de permissões --------------------------------------------


def grant_permissions(
    content_type: str,
    content_id: str,
    grantee_type: str,
    grantee_name: str,
    capabilities: dict[str, str],
) -> PermissionsResult | ToolError:
    """Concede capacidades a um usuário ou grupo em um item de conteúdo.

    Aplica permissões de forma idempotente: conceder uma capability já existente
    não gera erro. Antes de aplicar, realiza detecção eager de projeto bloqueado
    e validação de showTabs para views.

    Args:
        content_type: Tipo de conteúdo ('project', 'workbook', 'datasource',
            'view', 'flow', 'virtual_connection').
        content_id: LUID do item de conteúdo.
        grantee_type: 'user' ou 'group'.
        grantee_name: Nome do usuário ou grupo a receber as permissões.
        capabilities: Mapa de capability → modo.
            Ex.: {"Read": "Allow", "Write": "Deny"}.

    Returns:
        ``PermissionsResult`` com o estado atualizado das permissões do conteúdo,
        ou ``ToolError`` com código acionável.
    """
    # Validação de inputs
    ct = _validate_content_type(content_type)
    if isinstance(ct, ToolError):
        return ct

    err = _validate_grantee_type(grantee_type)
    if err is not None:
        return err

    err = _validate_capabilities(capabilities)
    if err is not None:
        return err

    try:
        with tableau_session(load_settings()) as client:
            # Resolver grantee
            resolved = _resolve_grantee(client, grantee_type, grantee_name)
            if isinstance(resolved, ToolError):
                return resolved
            grantee_id, _ = resolved

            # Check de projeto bloqueado (eager)
            lock_err = _check_locked_project(client, ct, content_id)
            if lock_err is not None:
                return lock_err

            # Construir e aplicar regra
            rule = _build_permission_rule(grantee_type, grantee_id, capabilities)
            client.update_permissions(ct, content_id, [rule])

            # Buscar estado atualizado
            updated_rules = client.get_permissions(ct, content_id)

            # Obter nome do conteúdo (best-effort)
            content_name = _get_content_name(client, ct, content_id)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    return _rules_to_permissions_result(updated_rules, ct, content_id, content_name)


def revoke_permissions(
    content_type: str,
    content_id: str,
    grantee_type: str,
    grantee_name: str,
    capabilities: list[str],
) -> PermissionsResult | ToolError:
    """Revoga capacidades de um usuário ou grupo em um item de conteúdo.

    Remove as capabilities listadas (independente do modo Allow/Deny). Antes
    de aplicar, realiza detecção eager de projeto bloqueado e validação de
    showTabs para views.

    Args:
        content_type: Tipo de conteúdo ('project', 'workbook', 'datasource',
            'view', 'flow', 'virtual_connection').
        content_id: LUID do item de conteúdo.
        grantee_type: 'user' ou 'group'.
        grantee_name: Nome do usuário ou grupo.
        capabilities: Lista de nomes de capability a remover. Ex.: ["Read", "Write"].

    Returns:
        ``PermissionsResult`` com o estado atualizado das permissões do conteúdo,
        ou ``ToolError`` com código acionável.
    """
    # Validação de inputs
    ct = _validate_content_type(content_type)
    if isinstance(ct, ToolError):
        return ct

    err = _validate_grantee_type(grantee_type)
    if err is not None:
        return err

    if not capabilities:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            "capabilities não pode ser vazio.",
        )

    try:
        with tableau_session(load_settings()) as client:
            # Resolver grantee
            resolved = _resolve_grantee(client, grantee_type, grantee_name)
            if isinstance(resolved, ToolError):
                return resolved
            grantee_id, _ = resolved

            # Check de projeto bloqueado (eager)
            lock_err = _check_locked_project(client, ct, content_id)
            if lock_err is not None:
                return lock_err

            # Buscar permissões atuais para descobrir o modo de cada capability
            current_rules = client.get_permissions(ct, content_id)
            caps_to_revoke = set(capabilities)

            # Localizar o modo de cada capability que pertence ao grantee
            for rule in current_rules:
                grantee = getattr(rule, "grantee", None)
                rule_grantee_id = getattr(grantee, "id", "") or getattr(
                    grantee, "_id", ""
                )
                if rule_grantee_id != grantee_id:
                    continue
                rule_caps = getattr(rule, "capabilities", {}) or {}
                for cap_name, cap_mode in rule_caps.items():
                    if cap_name in caps_to_revoke:
                        revoke_rule = _build_revoke_rule(
                            grantee_type, grantee_id, cap_name, cap_mode
                        )
                        client.delete_permission(ct, content_id, revoke_rule)

            # Buscar estado atualizado
            updated_rules = client.get_permissions(ct, content_id)

            # Obter nome do conteúdo (best-effort)
            content_name = _get_content_name(client, ct, content_id)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    return _rules_to_permissions_result(updated_rules, ct, content_id, content_name)


def list_permissions(
    content_type: str,
    content_id: str,
) -> PermissionsResult | ToolError:
    """Lista todas as permissões explícitas de um item de conteúdo.

    Operação somente de leitura — não realiza check de projeto bloqueado.

    Args:
        content_type: Tipo de conteúdo ('project', 'workbook', 'datasource',
            'view', 'flow', 'virtual_connection').
        content_id: LUID do item de conteúdo.

    Returns:
        ``PermissionsResult`` com todas as regras de permissão do conteúdo,
        ou ``ToolError`` com código acionável.
    """
    # Validação de input
    ct = _validate_content_type(content_type)
    if isinstance(ct, ToolError):
        return ct

    try:
        with tableau_session(load_settings()) as client:
            rules = client.get_permissions(ct, content_id)
            content_name = _get_content_name(client, ct, content_id)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    return _rules_to_permissions_result(rules, ct, content_id, content_name)


def _get_content_name(
    client: TableauClient, content_type: PermContentType, content_id: str
) -> str:
    """Obtém o nome do conteúdo a partir do client (best-effort).

    Se falhar, retorna string vazia em vez de propagar erro.
    """
    try:
        # Usa o dispatch interno: pega o item via get_by_id
        _, fetch_item = client._perm_dispatch[content_type]
        item = fetch_item(content_id)
        return getattr(item, "name", "") or ""
    except Exception:  # noqa: BLE001 - best-effort, não bloqueia o resultado
        return ""


# -- Helpers internos — default permissions ------------------------------------

# Tipos de conteúdo que suportam permissões padrão de projeto.
_VALID_DEFAULT_PERM_TYPES = frozenset(
    {"workbook", "datasource", "flow", "virtual_connection"}
)


def _validate_default_perm_content_type(
    for_content_type: str,
) -> PermContentType | ToolError:
    """Valida ``for_content_type`` contra os tipos suportados por default permissions.

    Diferente da validação genérica de content_type: apenas workbook, datasource,
    flow e virtual_connection são aceitos em operações de default permissions.
    """
    if for_content_type not in _VALID_DEFAULT_PERM_TYPES:
        valid = ", ".join(sorted(_VALID_DEFAULT_PERM_TYPES))
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"for_content_type '{for_content_type}' inválido para permissões padrão. "
            f"Valores aceitos: {valid}.",
        )
    return PermContentType(for_content_type)


def _rules_to_default_permissions_result(
    rules: list[object],
    project_id: str,
    project_name: str,
    for_content_type: PermContentType,
) -> DefaultPermissionsResult:
    """Converte lista de ``TSC.PermissionsRule`` para ``DefaultPermissionsResult``."""
    grantee_perms: list[GranteePermissions] = []
    for rule in rules:
        grantee = getattr(rule, "grantee", None)
        grantee_id = getattr(grantee, "id", "") or getattr(grantee, "_id", "")
        grantee_name_val = getattr(grantee, "name", None) or ""

        if isinstance(grantee, TSC.GroupItem):
            g_type = "group"
        else:
            g_type = "user"

        caps_dict = getattr(rule, "capabilities", {}) or {}
        caps = [
            CapabilityRule(name=cap_name, mode=cap_mode)
            for cap_name, cap_mode in caps_dict.items()
        ]

        grantee_perms.append(
            GranteePermissions(
                grantee_type=g_type,
                grantee_id=grantee_id,
                grantee_name=grantee_name_val,
                capabilities=caps,
            )
        )

    return DefaultPermissionsResult(
        project_id=project_id,
        project_name=project_name,
        for_content_type=for_content_type.value,
        permissions=grantee_perms,
    )


# -- Ferramentas de permissões padrão de projeto -------------------------------


def list_default_permissions(
    project_name: str,
    for_content_type: str,
) -> DefaultPermissionsResult | ToolError:
    """Lista as permissões padrão de um projeto para um tipo de conteúdo.

    Permissões padrão definem o que novos itens publicados em um projeto herdam
    automaticamente. Operação somente de leitura.

    Args:
        project_name: Nome exato do projeto.
        for_content_type: Tipo de conteúdo cujas permissões padrão devem ser
            listadas ('workbook', 'datasource', 'flow', 'virtual_connection').

    Returns:
        ``DefaultPermissionsResult`` com as regras padrão configuradas, ou
        ``ToolError`` com código acionável (PROJECT_NOT_FOUND, VALIDATION_ERROR).
    """
    # Validar content type
    ct = _validate_default_perm_content_type(for_content_type)
    if isinstance(ct, ToolError):
        return ct

    try:
        with tableau_session(load_settings()) as client:
            # Resolver projeto por nome
            project_id = client.find_project_id(project_name)
            if project_id is None:
                return ToolError.of(
                    ErrorCode.PROJECT_NOT_FOUND,
                    f"Projeto '{project_name}' não encontrado.",
                )

            # Buscar permissões padrão
            rules = client.get_default_permissions(project_id, ct)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    return _rules_to_default_permissions_result(rules, project_id, project_name, ct)


def set_default_permissions(
    project_name: str,
    for_content_type: str,
    grantee_type: str,
    grantee_name: str,
    capabilities: dict[str, str],
) -> DefaultPermissionsResult | ToolError:
    """Define permissões padrão em um projeto para um tipo de conteúdo.

    Configura as permissões que novos itens do tipo especificado herdarão ao serem
    publicados no projeto. A operação é aditiva: aplica as capabilities informadas
    sem remover regras existentes de outros grantees.

    Args:
        project_name: Nome exato do projeto.
        for_content_type: Tipo de conteúdo ('workbook', 'datasource', 'flow',
            'virtual_connection').
        grantee_type: 'user' ou 'group'.
        grantee_name: Nome do usuário ou grupo a receber as permissões padrão.
        capabilities: Mapa de capability → modo.
            Ex.: {"Read": "Allow", "ExportData": "Deny"}.

    Returns:
        ``DefaultPermissionsResult`` com o estado atualizado das permissões
        padrão, ou ``ToolError`` com código acionável.
    """
    # Validar inputs
    ct = _validate_default_perm_content_type(for_content_type)
    if isinstance(ct, ToolError):
        return ct

    err = _validate_grantee_type(grantee_type)
    if err is not None:
        return err

    err = _validate_capabilities(capabilities)
    if err is not None:
        return err

    try:
        with tableau_session(load_settings()) as client:
            # Resolver projeto por nome
            project_id = client.find_project_id(project_name)
            if project_id is None:
                return ToolError.of(
                    ErrorCode.PROJECT_NOT_FOUND,
                    f"Projeto '{project_name}' não encontrado.",
                )

            # Resolver grantee
            resolved = _resolve_grantee(client, grantee_type, grantee_name)
            if isinstance(resolved, ToolError):
                return resolved
            grantee_id, _ = resolved

            # Construir regra e aplicar
            rule = _build_permission_rule(grantee_type, grantee_id, capabilities)
            client.update_default_permissions(project_id, ct, [rule])

            # Buscar estado atualizado
            updated_rules = client.get_default_permissions(project_id, ct)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    return _rules_to_default_permissions_result(
        updated_rules, project_id, project_name, ct
    )


# -- Effective Permissions (Phase 2) -------------------------------------------

# Todas as capabilities conhecidas do Tableau que devem ser avaliadas.
_ALL_CAPABILITIES = frozenset(
    {
        "View",
        "Publish",
        "Read",
        "Filter",
        "ViewComments",
        "AddComment",
        "ExportImage",
        "ExportData",
        "ShareView",
        "ViewUnderlyingData",
        "WebEdit",
        "DownloadWorkbook",
        "Write",
        "CreateRefreshMetrics",
        "Move",
        "Delete",
        "ChangePermissions",
        "RefreshExtracts",
        "ExportXml",
        "Connect",
        "DownloadDatasource",
        "CreateMetricDefinitions",
        "DownloadFlow",
        "WebEditFlow",
        "RunFlow",
        "Execute",
        "ChangeHierarchy",
        "RunExplainData",
    }
)


def _compute_effective_capabilities(
    user_id: str,
    site_role: str,
    is_owner: bool,
    is_admin: bool,
    rules: list[object],
    user_group_ids: set[str],
) -> list[EffectiveCapability]:
    """Algoritmo puro de avaliação de permissões efetivas (ADR-002).

    Ordem de avaliação:
    1. Admin bypass → todas Allow com reason "admin"
    2. Ownership → todas Allow com reason "ownership"
    3. Para cada capability:
       a. Se existe regra explícita no nível de usuário → usa o modo (reason: user_rule)
       b. Senão, agrega regras dos grupos do usuário:
          - Se QUALQUER grupo tem Deny → Deny (reason: group_rule, Deny-wins)
          - Se ALGUM grupo tem Allow e NENHUM tem Deny → Allow (reason: group_rule)
       c. Senão → Deny (reason: not_granted)
    4. Aplica teto do site role: se o resultado é Allow mas a capability não está no
       SITE_ROLE_CAPS do role → Deny (reason: site_role_cap)
    """
    # Descobrir quais capabilities estão presentes nas regras
    caps_in_rules: set[str] = set()
    for rule in rules:
        caps_dict = getattr(rule, "capabilities", {}) or {}
        caps_in_rules.update(caps_dict.keys())

    # Usar apenas capabilities que aparecem nas regras + _ALL_CAPABILITIES conhecidas
    all_caps = sorted(caps_in_rules | _ALL_CAPABILITIES)

    # Admin bypass
    if is_admin:
        return [
            EffectiveCapability(name=cap, mode="Allow", reason="admin")
            for cap in all_caps
        ]

    # Ownership override
    if is_owner:
        return [
            EffectiveCapability(name=cap, mode="Allow", reason="ownership")
            for cap in all_caps
        ]

    # Separar regras por tipo (user vs group)
    user_caps: dict[str, str] = {}  # cap_name → mode
    group_caps: dict[str, list[str]] = {}  # cap_name → [modes from groups]

    for rule in rules:
        grantee = getattr(rule, "grantee", None)
        grantee_id = getattr(grantee, "id", "") or getattr(grantee, "_id", "")
        caps_dict = getattr(rule, "capabilities", {}) or {}

        if isinstance(grantee, TSC.UserItem):
            if grantee_id == user_id:
                for cap_name, mode in caps_dict.items():
                    user_caps[cap_name] = mode
        elif isinstance(grantee, TSC.GroupItem):
            if grantee_id in user_group_ids:
                for cap_name, mode in caps_dict.items():
                    if cap_name not in group_caps:
                        group_caps[cap_name] = []
                    group_caps[cap_name].append(mode)

    # Obter teto do site role
    role_caps = SITE_ROLE_CAPS.get(site_role)

    results: list[EffectiveCapability] = []
    for cap in all_caps:
        mode: str
        reason: str

        # Passo 3a: regra explícita de usuário
        if cap in user_caps:
            mode = user_caps[cap]
            reason = "user_rule"
        # Passo 3b: agregação de grupos (Deny-wins)
        elif cap in group_caps:
            modes = group_caps[cap]
            if "Deny" in modes:
                mode = "Deny"
                reason = "group_rule"
            else:
                mode = "Allow"
                reason = "group_rule"
        # Passo 3c: nenhuma regra
        else:
            mode = "Deny"
            reason = "not_granted"

        # Passo 4: teto do site role (apenas se temos mapeamento para o role)
        if mode == "Allow" and role_caps is not None and cap not in role_caps:
            mode = "Deny"
            reason = "site_role_cap"

        results.append(EffectiveCapability(name=cap, mode=mode, reason=reason))

    return results


def _build_summary(
    capabilities: list[EffectiveCapability],
    is_admin: bool,
    is_owner: bool,
    site_role: str,
) -> str:
    """Gera resumo legível das permissões efetivas."""
    if is_admin:
        return f"Acesso total (admin bypass, site role: {site_role})."

    if is_owner:
        return f"Acesso total como proprietário do conteúdo (site role: {site_role})."

    allowed = [c.name for c in capabilities if c.mode == "Allow"]
    denied = [c.name for c in capabilities if c.mode == "Deny"]

    if not allowed:
        return (
            f"Sem acesso efetivo (site role: {site_role}). "
            "Todas as capabilities negadas."
        )

    if not denied:
        return (
            f"Acesso completo (site role: {site_role}). "
            f"Capabilities: {', '.join(allowed)}."
        )

    return (
        f"Acesso parcial (site role: {site_role}). "
        f"Permitido: {', '.join(allowed[:10])}"
        f"{'...' if len(allowed) > 10 else ''}. "
        f"Negado: {', '.join(denied[:10])}"
        f"{'...' if len(denied) > 10 else ''}."
    )


def effective_permissions(
    content_type: str,
    content_id: str,
    user_name: str,
) -> EffectivePermissionsResult | ToolError:
    """Computa as permissões efetivas de um usuário em um item de conteúdo.

    Resultado **computado localmente** (não autoritativo): combina regras
    explícitas de permissão, agregação de grupos (Deny-wins), teto do site role
    e overrides de propriedade/admin conforme ADR-002.

    O algoritmo:
    1. Resolve o usuário e obtém site role.
    2. Verifica se é admin (bypass total) ou proprietário (acesso total).
    3. Busca permissões raw do conteúdo.
    4. Para grupos com regras no conteúdo, verifica membros para identificar
       os grupos do usuário (lazy-fetch, evita listar TODOS os grupos).
    5. Aplica: regras de usuário → agregação de grupo (Deny-wins) → teto site role.

    Args:
        content_type: Tipo de conteúdo ('project', 'workbook', 'datasource',
            'view', 'flow', 'virtual_connection').
        content_id: LUID do item de conteúdo.
        user_name: Nome exato do usuário cujas permissões efetivas serão calculadas.

    Returns:
        ``EffectivePermissionsResult`` com capabilities efetivas e resumo, ou
        ``ToolError`` com código ``NOT_FOUND`` ou erro de rede/auth.
    """
    # Validação de content_type
    ct = _validate_content_type(content_type)
    if isinstance(ct, ToolError):
        return ct

    try:
        with tableau_session(load_settings()) as client:
            # 1. Resolver usuário
            try:
                user_id, site_role = client.resolve_user(user_name)
            except TableauClientError as exc:
                return ToolError.of(exc.code, exc.message)

            # 2. Verificar admin
            is_admin = site_role in _ADMIN_SITE_ROLES

            # 3. Buscar permissões raw do conteúdo (também valida que o conteúdo existe)
            try:
                rules = client.get_permissions(ct, content_id)
            except TableauClientError as exc:
                return ToolError.of(exc.code, exc.message)

            # 4. Verificar ownership
            is_owner = False
            try:
                _, fetch_item = client._perm_dispatch[ct]
                item = fetch_item(content_id)
                owner_id = getattr(item, "owner_id", None)
                if owner_id == user_id:
                    is_owner = True
            except Exception:  # noqa: BLE001 - best-effort ownership check
                pass

            # 5. Identificar grupos do usuário que têm regras no conteúdo (lazy)
            user_group_ids: set[str] = set()
            if not is_admin and not is_owner:
                # Coletar IDs de grupos que aparecem nas regras
                group_ids_in_rules: set[str] = set()
                for rule in rules:
                    grantee = getattr(rule, "grantee", None)
                    if isinstance(grantee, TSC.GroupItem):
                        grantee_id = getattr(grantee, "id", "") or getattr(
                            grantee, "_id", ""
                        )
                        if grantee_id:
                            group_ids_in_rules.add(grantee_id)

                # Para cada grupo com regras, verificar se o usuário é membro
                for group_id in group_ids_in_rules:
                    try:
                        members = client.list_group_members(group_id)
                        for member_id, _, _ in members:
                            if member_id == user_id:
                                user_group_ids.add(group_id)
                                break
                    except TableauClientError:
                        # Se não conseguir listar membros, ignora o grupo
                        pass

    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    # 6. Avaliar capabilities efetivas (lógica pura)
    capabilities = _compute_effective_capabilities(
        user_id=user_id,
        site_role=site_role,
        is_owner=is_owner,
        is_admin=is_admin,
        rules=rules,
        user_group_ids=user_group_ids,
    )

    # 7. Gerar resumo
    summary = _build_summary(capabilities, is_admin, is_owner, site_role)

    return EffectivePermissionsResult(
        content_type=ct.value,
        content_id=content_id,
        user_id=user_id,
        user_name=user_name,
        site_role=site_role,
        is_owner=is_owner,
        is_admin=is_admin,
        capabilities=capabilities,
        summary=summary,
    )


# -- Registro ------------------------------------------------------------------


def register(mcp: FastMCP) -> None:
    """Registra as ferramentas de permissões na instância FastMCP."""
    mcp.tool(list_users)
    mcp.tool(list_groups)
    mcp.tool(resolve_user)
    mcp.tool(resolve_group)
    mcp.tool(list_group_members)
    mcp.tool(grant_permissions)
    mcp.tool(revoke_permissions)
    mcp.tool(list_permissions)
    mcp.tool(list_default_permissions)
    mcp.tool(set_default_permissions)
    mcp.tool(effective_permissions)

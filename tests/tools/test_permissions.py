"""Testes unitários das tools de permissões (`tools/permissions.py`).

Cobre as ferramentas de resolução (task_04) e as ferramentas CRUD de permissões
(task_05: grant_permissions, revoke_permissions, list_permissions).

O `TableauClient` e a sessão (`tableau_session`/`load_settings`) são sempre
mockados no limite da integração — sem rede e sem Tableau real. Segue o padrão
de monkeypatch-at-tool-module já consolidado em `test_deploy.py`.
"""

from unittest.mock import MagicMock, PropertyMock

import pytest
import tableauserverclient as TSC

from mcp_tableau.models import (
    DefaultPermissionsResult,
    ErrorCode,
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
from mcp_tableau.tableau.client import TableauClientError
from mcp_tableau.tools import permissions


def _make_tsc_rule(
    grantee_type: str = "user",
    grantee_id: str = "u-1",
    grantee_name: str = "alice",
    capabilities: dict[str, str] | None = None,
) -> MagicMock:
    """Cria um mock de TSC.PermissionsRule para testes."""
    rule = MagicMock()
    if grantee_type == "group":
        grantee = TSC.GroupItem()
        grantee._id = grantee_id
        grantee.name = grantee_name
    else:
        grantee = TSC.UserItem()
        grantee._id = grantee_id
        grantee.name = grantee_name
    rule.grantee = grantee
    rule.capabilities = capabilities or {"Read": "Allow"}
    return rule


@pytest.fixture
def client() -> MagicMock:
    """Mock do `TableauClient` com métodos de resolução e permissões."""
    mock = MagicMock(name="TableauClient")
    # Defaults: listas vazias / resolve retorna dados fictícios
    mock.list_users.return_value = []
    mock.list_groups.return_value = []
    mock.resolve_user.return_value = ("u-1", "Creator")
    mock.resolve_group.return_value = ("g-1", 5)
    mock.list_group_members.return_value = []
    # Permission CRUD defaults
    mock.get_content_project_id.return_value = "proj-1"
    mock.get_project_lock_state.return_value = "ManagedByOwner"
    mock.get_permissions.return_value = []
    mock.update_permissions.return_value = []
    mock.delete_permission.return_value = None
    # Default permissions defaults
    mock.find_project_id.return_value = "proj-1"
    mock.get_default_permissions.return_value = []
    mock.update_default_permissions.return_value = []
    # _perm_dispatch for _get_content_name
    mock_item = MagicMock()
    mock_item.name = "Test Content"
    mock_dispatch = {
        PermContentType.workbook: (MagicMock(), MagicMock(return_value=mock_item)),
        PermContentType.datasource: (MagicMock(), MagicMock(return_value=mock_item)),
        PermContentType.project: (MagicMock(), MagicMock(return_value=mock_item)),
        PermContentType.view: (MagicMock(), MagicMock(return_value=mock_item)),
        PermContentType.flow: (MagicMock(), MagicMock(return_value=mock_item)),
        PermContentType.virtual_connection: (
            MagicMock(),
            MagicMock(return_value=mock_item),
        ),
    }
    type(mock)._perm_dispatch = PropertyMock(return_value=mock_dispatch)
    return mock


@pytest.fixture
def session(client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Monkeypatcha `tableau_session`/`load_settings` no módulo `permissions`.

    `tableau_session` vira um context manager que produz o `client` mock; a
    `load_settings` retorna um `MagicMock`. Retorna o mock de `tableau_session`
    para asserts de "não chamou o client".
    """
    session_cm = MagicMock(name="tableau_session")
    session_cm.return_value.__enter__.return_value = client
    session_cm.return_value.__exit__.return_value = False
    monkeypatch.setattr(permissions, "tableau_session", session_cm)
    monkeypatch.setattr(
        permissions, "load_settings", MagicMock(return_value=MagicMock())
    )
    return session_cm


# ==============================================================================
# list_users
# ==============================================================================


class TestListUsers:
    """Testes para a ferramenta `list_users`."""

    def test_sem_filtro_retorna_user_list_result_com_usuarios(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_users.return_value = [
            ("u-1", "alice", "Creator"),
            ("u-2", "bob", "Viewer"),
        ]

        result = permissions.list_users()

        assert isinstance(result, UserListResult)
        assert result.status == "success"
        assert result.total_count == 2
        assert len(result.users) == 2
        assert result.users[0] == UserInfo(id="u-1", name="alice", site_role="Creator")
        assert result.users[1] == UserInfo(id="u-2", name="bob", site_role="Viewer")
        client.list_users.assert_called_once_with(None)

    def test_com_filtro_passa_name_filter_ao_client(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_users.return_value = [("u-1", "alice", "Creator")]

        result = permissions.list_users(name_filter="alice")

        assert isinstance(result, UserListResult)
        assert result.total_count == 1
        assert result.users[0].name == "alice"
        client.list_users.assert_called_once_with("alice")

    def test_lista_vazia_retorna_total_count_zero(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_users.return_value = []

        result = permissions.list_users(name_filter="inexistente")

        assert isinstance(result, UserListResult)
        assert result.total_count == 0
        assert result.users == []

    def test_erro_auth_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_users.side_effect = TableauClientError(
            ErrorCode.AUTH_FAILED, "Token expirado."
        )

        result = permissions.list_users()

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.AUTH_FAILED
        assert "Token expirado" in result.error.message

    def test_erro_upstream_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_users.side_effect = TableauClientError(
            ErrorCode.UPSTREAM_ERROR, "Falha na API REST."
        )

        result = permissions.list_users()

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.UPSTREAM_ERROR


# ==============================================================================
# list_groups
# ==============================================================================


class TestListGroups:
    """Testes para a ferramenta `list_groups`."""

    def test_sem_filtro_retorna_group_list_result_com_grupos(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_groups.return_value = [
            ("g-1", "Analysts", 10),
            ("g-2", "Admins", 3),
        ]

        result = permissions.list_groups()

        assert isinstance(result, GroupListResult)
        assert result.status == "success"
        assert result.total_count == 2
        assert len(result.groups) == 2
        assert result.groups[0] == GroupInfo(id="g-1", name="Analysts", user_count=10)
        assert result.groups[1] == GroupInfo(id="g-2", name="Admins", user_count=3)
        client.list_groups.assert_called_once_with(None)

    def test_com_filtro_passa_name_filter_ao_client(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_groups.return_value = [("g-1", "Analysts", 10)]

        result = permissions.list_groups(name_filter="Analysts")

        assert isinstance(result, GroupListResult)
        assert result.total_count == 1
        assert result.groups[0].name == "Analysts"
        client.list_groups.assert_called_once_with("Analysts")

    def test_grupo_com_user_count_none(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_groups.return_value = [("g-3", "NoCount", None)]

        result = permissions.list_groups()

        assert isinstance(result, GroupListResult)
        assert result.groups[0].user_count is None

    def test_lista_vazia_retorna_total_count_zero(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_groups.return_value = []

        result = permissions.list_groups()

        assert isinstance(result, GroupListResult)
        assert result.total_count == 0
        assert result.groups == []

    def test_erro_auth_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.list_groups.side_effect = TableauClientError(
            ErrorCode.AUTH_FAILED, "Credenciais inválidas."
        )

        result = permissions.list_groups()

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.AUTH_FAILED


# ==============================================================================
# resolve_user
# ==============================================================================


class TestResolveUser:
    """Testes para a ferramenta `resolve_user`."""

    def test_usuario_existente_retorna_resolve_result(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_user.return_value = ("u-abc", "Explorer")

        result = permissions.resolve_user(name="alice")

        assert isinstance(result, ResolveResult)
        assert result.status == "success"
        assert result.id == "u-abc"
        assert result.name == "alice"
        assert result.site_role == "Explorer"
        client.resolve_user.assert_called_once_with("alice")

    def test_usuario_inexistente_retorna_tool_error_not_found(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_user.side_effect = TableauClientError(
            ErrorCode.NOT_FOUND, "Usuário 'ghost' não encontrado no site."
        )

        result = permissions.resolve_user(name="ghost")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.NOT_FOUND
        assert "ghost" in result.error.message

    def test_erro_auth_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_user.side_effect = TableauClientError(
            ErrorCode.AUTH_FAILED, "Sessão expirada."
        )

        result = permissions.resolve_user(name="alice")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.AUTH_FAILED

    def test_usuario_com_site_role_vazio(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_user.return_value = ("u-xyz", "")

        result = permissions.resolve_user(name="noRole")

        assert isinstance(result, ResolveResult)
        assert result.site_role == ""


# ==============================================================================
# resolve_group
# ==============================================================================


class TestResolveGroup:
    """Testes para a ferramenta `resolve_group`."""

    def test_grupo_existente_retorna_resolve_result(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.return_value = ("g-abc", 7)

        result = permissions.resolve_group(name="Analysts")

        assert isinstance(result, ResolveResult)
        assert result.status == "success"
        assert result.id == "g-abc"
        assert result.name == "Analysts"
        assert result.site_role is None  # grupos não têm site_role
        client.resolve_group.assert_called_once_with("Analysts")

    def test_grupo_inexistente_retorna_tool_error_not_found(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.side_effect = TableauClientError(
            ErrorCode.NOT_FOUND, "Grupo 'fantasma' não encontrado no site."
        )

        result = permissions.resolve_group(name="fantasma")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.NOT_FOUND
        assert "fantasma" in result.error.message

    def test_erro_auth_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.side_effect = TableauClientError(
            ErrorCode.AUTH_FAILED, "Token inválido."
        )

        result = permissions.resolve_group(name="Admins")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.AUTH_FAILED


# ==============================================================================
# list_group_members
# ==============================================================================


class TestListGroupMembers:
    """Testes para a ferramenta `list_group_members`."""

    def test_grupo_valido_retorna_group_members_result(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.return_value = ("g-1", 2)
        client.list_group_members.return_value = [
            ("u-1", "alice", "Creator"),
            ("u-2", "bob", "Viewer"),
        ]

        result = permissions.list_group_members(group_name="Analysts")

        assert isinstance(result, GroupMembersResult)
        assert result.status == "success"
        assert result.group_id == "g-1"
        assert result.group_name == "Analysts"
        assert len(result.members) == 2
        assert result.members[0] == UserInfo(
            id="u-1", name="alice", site_role="Creator"
        )
        assert result.members[1] == UserInfo(id="u-2", name="bob", site_role="Viewer")
        client.resolve_group.assert_called_once_with("Analysts")
        client.list_group_members.assert_called_once_with("g-1")

    def test_grupo_inexistente_retorna_tool_error_not_found(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.side_effect = TableauClientError(
            ErrorCode.NOT_FOUND, "Grupo 'fantasma' não encontrado no site."
        )

        result = permissions.list_group_members(group_name="fantasma")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.NOT_FOUND
        assert "fantasma" in result.error.message
        client.list_group_members.assert_not_called()

    def test_grupo_sem_membros_retorna_lista_vazia(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.return_value = ("g-empty", 0)
        client.list_group_members.return_value = []

        result = permissions.list_group_members(group_name="EmptyGroup")

        assert isinstance(result, GroupMembersResult)
        assert result.group_id == "g-empty"
        assert result.group_name == "EmptyGroup"
        assert result.members == []

    def test_erro_auth_na_resolucao_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.side_effect = TableauClientError(
            ErrorCode.AUTH_FAILED, "Sessão expirada."
        )

        result = permissions.list_group_members(group_name="Analysts")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.AUTH_FAILED

    def test_erro_auth_na_listagem_de_membros_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.return_value = ("g-1", 5)
        client.list_group_members.side_effect = TableauClientError(
            ErrorCode.AUTH_FAILED, "Token expirado durante listagem."
        )

        result = permissions.list_group_members(group_name="Analysts")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.AUTH_FAILED

    def test_erro_upstream_na_listagem_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        client.resolve_group.return_value = ("g-1", 5)
        client.list_group_members.side_effect = TableauClientError(
            ErrorCode.UPSTREAM_ERROR, "Erro interno do Tableau."
        )

        result = permissions.list_group_members(group_name="Analysts")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.UPSTREAM_ERROR


# ==============================================================================
# register
# ==============================================================================


class TestRegister:
    """Testes para a função `register(mcp)`."""

    def test_registra_dez_ferramentas(self) -> None:
        mcp = MagicMock(name="FastMCP")

        permissions.register(mcp)

        assert mcp.tool.call_count == 10
        registered = [call.args[0] for call in mcp.tool.call_args_list]
        assert permissions.list_users in registered
        assert permissions.list_groups in registered
        assert permissions.resolve_user in registered
        assert permissions.resolve_group in registered
        assert permissions.list_group_members in registered
        assert permissions.grant_permissions in registered
        assert permissions.revoke_permissions in registered
        assert permissions.list_permissions in registered
        assert permissions.list_default_permissions in registered
        assert permissions.set_default_permissions in registered


# ==============================================================================
# Sessão não aberta quando não necessária
# ==============================================================================


class TestSessionNotOpened:
    """Verifica que a sessão é sempre aberta (sem validação pré-rede)."""

    def test_list_users_abre_sessao(self, session: MagicMock) -> None:
        """list_users sempre abre sessão (não há validação pré-rede)."""
        permissions.list_users()
        session.assert_called_once()

    def test_resolve_user_abre_sessao(self, session: MagicMock) -> None:
        """resolve_user sempre abre sessão."""
        permissions.resolve_user(name="test")
        session.assert_called_once()


# ==============================================================================
# grant_permissions
# ==============================================================================


class TestGrantPermissions:
    """Testes para a ferramenta `grant_permissions`."""

    def test_happy_path_retorna_permissions_result(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """grant_permissions com inputs válidos retorna PermissionsResult."""
        updated_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow", "Write": "Allow"},
        )
        client.get_permissions.return_value = [updated_rule]

        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow", "Write": "Allow"},
        )

        assert isinstance(result, PermissionsResult)
        assert result.status == "success"
        assert result.content_type == "workbook"
        assert result.content_id == "wb-1"
        assert len(result.permissions) == 1
        assert result.permissions[0].grantee_type == "user"
        assert result.permissions[0].grantee_id == "u-1"
        assert len(result.permissions[0].capabilities) == 2
        client.resolve_user.assert_called_once_with("alice")
        client.update_permissions.assert_called_once()

    def test_content_type_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """content_type inválido retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.grant_permissions(
            content_type="invalid_type",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "invalid_type" in result.error.message
        session.assert_not_called()

    def test_grantee_type_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """grantee_type inválido retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="role",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "role" in result.error.message
        session.assert_not_called()

    def test_capabilities_vazio_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """capabilities vazio retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "vazio" in result.error.message
        session.assert_not_called()

    def test_capabilities_modo_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """grant_permissions com modo inválido em capabilities retorna ToolError."""
        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Grant"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "Grant" in result.error.message
        session.assert_not_called()

    def test_grantee_nao_encontrado_retorna_not_found(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """grant_permissions com grantee inexistente retorna ToolError(NOT_FOUND)."""
        client.resolve_user.side_effect = TableauClientError(
            ErrorCode.NOT_FOUND, "Usuário 'ghost' não encontrado no site."
        )

        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="ghost",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.NOT_FOUND
        assert "ghost" in result.error.message
        client.update_permissions.assert_not_called()

    def test_projeto_bloqueado_retorna_locked_project_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """grant_permissions em projeto bloqueado retorna ToolError(LOCKED_PROJECT)."""
        client.get_project_lock_state.return_value = "LockedToProject"

        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.LOCKED_PROJECT
        msg = result.error.message.lower()
        assert "bloqueado" in msg or "locked" in msg
        assert "set_default_permissions" in result.error.message
        client.update_permissions.assert_not_called()

    def test_project_content_type_pula_lock_check(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """grant_permissions no tipo 'project' não verifica lock state."""
        updated_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )
        client.get_permissions.return_value = [updated_rule]

        result = permissions.grant_permissions(
            content_type="project",
            content_id="proj-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, PermissionsResult)
        client.get_content_project_id.assert_not_called()
        client.get_project_lock_state.assert_not_called()

    def test_idempotente_regranting_sucede(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """grant_permissions idempotente: re-conceder mesma capability não gera erro."""
        updated_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )
        client.get_permissions.return_value = [updated_rule]

        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, PermissionsResult)
        assert result.status == "success"

    def test_grant_com_grupo(self, client: MagicMock, session: MagicMock) -> None:
        """grant_permissions com grantee_type='group' resolve grupo."""
        updated_rule = _make_tsc_rule(
            grantee_type="group",
            grantee_id="g-1",
            grantee_name="Analysts",
            capabilities={"Read": "Allow"},
        )
        client.get_permissions.return_value = [updated_rule]

        result = permissions.grant_permissions(
            content_type="datasource",
            content_id="ds-1",
            grantee_type="group",
            grantee_name="Analysts",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, PermissionsResult)
        assert result.permissions[0].grantee_type == "group"
        client.resolve_group.assert_called_once_with("Analysts")

    def test_show_tabs_enabled_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """View com showTabs=true retorna ToolError(SHOW_TABS_ENABLED)."""
        client.update_permissions.side_effect = TableauClientError(
            ErrorCode.SHOW_TABS_ENABLED,
            "O workbook pai tem 'showTabs' habilitado. "
            "Permissões em nível de view são ignoradas pelo Tableau nesse modo.",
        )

        result = permissions.grant_permissions(
            content_type="view",
            content_id="v-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.SHOW_TABS_ENABLED
        assert "showTabs" in result.error.message

    def test_tableau_client_error_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """TableauClientError durante update_permissions é convertido em ToolError."""
        client.update_permissions.side_effect = TableauClientError(
            ErrorCode.UPSTREAM_ERROR, "Falha no Tableau."
        )

        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.UPSTREAM_ERROR

    def test_grant_deny_mode(self, client: MagicMock, session: MagicMock) -> None:
        """grant_permissions com modo 'Deny' é aceito e aplicado."""
        updated_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Write": "Deny"},
        )
        client.get_permissions.return_value = [updated_rule]

        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Write": "Deny"},
        )

        assert isinstance(result, PermissionsResult)
        assert result.permissions[0].capabilities[0].mode == "Deny"

    def test_locked_to_project_without_nested(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """LockedToProjectWithoutNested also triggers lock error."""
        client.get_project_lock_state.return_value = "LockedToProjectWithoutNested"

        result = permissions.grant_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.LOCKED_PROJECT


# ==============================================================================
# revoke_permissions
# ==============================================================================


class TestRevokePermissions:
    """Testes para a ferramenta `revoke_permissions`."""

    def test_happy_path_retorna_permissions_result_sem_capability_revogada(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """revoke_permissions remove capabilities e retorna estado atualizado."""
        existing_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow", "Write": "Allow"},
        )
        # Primeira chamada: get_permissions retorna as regras atuais
        # Segunda chamada: get_permissions retorna regras atualizadas (sem Write)
        remaining_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )
        client.get_permissions.side_effect = [[existing_rule], [remaining_rule]]

        result = permissions.revoke_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities=["Write"],
        )

        assert isinstance(result, PermissionsResult)
        assert result.status == "success"
        assert result.content_type == "workbook"
        assert result.content_id == "wb-1"
        # The updated permissions should only have Read
        assert len(result.permissions) == 1
        cap_names = [c.name for c in result.permissions[0].capabilities]
        assert "Read" in cap_names
        assert "Write" not in cap_names
        client.delete_permission.assert_called_once()

    def test_content_type_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """revoke_permissions com content_type inválido retorna ToolError."""
        result = permissions.revoke_permissions(
            content_type="bad_type",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities=["Read"],
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR

    def test_grantee_type_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """revoke_permissions com grantee_type inválido retorna ToolError."""
        result = permissions.revoke_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="admin",
            grantee_name="alice",
            capabilities=["Read"],
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR

    def test_capabilities_vazio_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """revoke_permissions com lista de capabilities vazia retorna ToolError."""
        result = permissions.revoke_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities=[],
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "vazio" in result.error.message

    def test_projeto_bloqueado_retorna_locked_project_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """revoke_permissions em projeto bloqueado retorna ToolError(LOCKED_PROJECT)."""
        client.get_project_lock_state.return_value = "LockedToProject"

        result = permissions.revoke_permissions(
            content_type="datasource",
            content_id="ds-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities=["Read"],
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.LOCKED_PROJECT
        assert "set_default_permissions" in result.error.message
        client.delete_permission.assert_not_called()

    def test_grantee_nao_encontrado_retorna_not_found(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """revoke_permissions com grantee inexistente retorna ToolError(NOT_FOUND)."""
        client.resolve_user.side_effect = TableauClientError(
            ErrorCode.NOT_FOUND, "Usuário 'ghost' não encontrado."
        )

        result = permissions.revoke_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="ghost",
            capabilities=["Read"],
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.NOT_FOUND

    def test_revoke_multiplas_capabilities(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """revoke_permissions remove múltiplas capabilities de uma vez."""
        existing_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow", "Write": "Allow", "ExportData": "Allow"},
        )
        empty_result = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"ExportData": "Allow"},
        )
        client.get_permissions.side_effect = [[existing_rule], [empty_result]]

        result = permissions.revoke_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities=["Read", "Write"],
        )

        assert isinstance(result, PermissionsResult)
        assert client.delete_permission.call_count == 2

    def test_show_tabs_enabled_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """revoke_permissions em view com showTabs=true retorna ToolError."""
        existing_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )
        client.get_permissions.return_value = [existing_rule]
        client.delete_permission.side_effect = TableauClientError(
            ErrorCode.SHOW_TABS_ENABLED,
            "O workbook pai tem 'showTabs' habilitado.",
        )

        result = permissions.revoke_permissions(
            content_type="view",
            content_id="v-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities=["Read"],
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.SHOW_TABS_ENABLED

    def test_tableau_client_error_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """TableauClientError durante revoke é convertido em ToolError."""
        client.get_permissions.side_effect = TableauClientError(
            ErrorCode.UPSTREAM_ERROR, "Falha no Tableau."
        )

        result = permissions.revoke_permissions(
            content_type="workbook",
            content_id="wb-1",
            grantee_type="user",
            grantee_name="alice",
            capabilities=["Read"],
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.UPSTREAM_ERROR

    def test_revoke_com_grupo(self, client: MagicMock, session: MagicMock) -> None:
        """revoke_permissions com grantee_type='group' resolve grupo."""
        existing_rule = _make_tsc_rule(
            grantee_type="group",
            grantee_id="g-1",
            grantee_name="Analysts",
            capabilities={"Read": "Allow"},
        )
        client.get_permissions.side_effect = [[existing_rule], []]

        result = permissions.revoke_permissions(
            content_type="datasource",
            content_id="ds-1",
            grantee_type="group",
            grantee_name="Analysts",
            capabilities=["Read"],
        )

        assert isinstance(result, PermissionsResult)
        client.resolve_group.assert_called_once_with("Analysts")


# ==============================================================================
# list_permissions
# ==============================================================================


class TestListPermissions:
    """Testes para a ferramenta `list_permissions`."""

    def test_retorna_permissions_result_com_todos_grantees(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """list_permissions retorna PermissionsResult com todas as regras."""
        user_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow", "Write": "Allow"},
        )
        group_rule = _make_tsc_rule(
            grantee_type="group",
            grantee_id="g-1",
            grantee_name="Analysts",
            capabilities={"Read": "Allow"},
        )
        client.get_permissions.return_value = [user_rule, group_rule]

        result = permissions.list_permissions(
            content_type="workbook",
            content_id="wb-1",
        )

        assert isinstance(result, PermissionsResult)
        assert result.status == "success"
        assert result.content_type == "workbook"
        assert result.content_id == "wb-1"
        assert len(result.permissions) == 2
        assert result.permissions[0].grantee_type == "user"
        assert result.permissions[0].grantee_name == "alice"
        assert result.permissions[1].grantee_type == "group"
        assert result.permissions[1].grantee_name == "Analysts"

    def test_content_type_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """list_permissions com content_type inválido retorna ToolError."""
        result = permissions.list_permissions(
            content_type="unknown",
            content_id="x-1",
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        session.assert_not_called()

    def test_projeto_bloqueado_nao_bloqueia_leitura(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """list_permissions em projeto bloqueado funciona (operação de leitura)."""
        client.get_project_lock_state.return_value = "LockedToProject"
        client.get_permissions.return_value = []

        result = permissions.list_permissions(
            content_type="workbook",
            content_id="wb-1",
        )

        assert isinstance(result, PermissionsResult)
        # list_permissions não chama get_project_lock_state
        client.get_project_lock_state.assert_not_called()

    def test_sem_permissoes_retorna_lista_vazia(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """list_permissions sem regras retorna permissions=[]."""
        client.get_permissions.return_value = []

        result = permissions.list_permissions(
            content_type="project",
            content_id="p-1",
        )

        assert isinstance(result, PermissionsResult)
        assert result.permissions == []

    def test_tableau_client_error_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """TableauClientError é convertido em ToolError."""
        client.get_permissions.side_effect = TableauClientError(
            ErrorCode.NOT_FOUND, "Conteúdo não encontrado."
        )

        result = permissions.list_permissions(
            content_type="workbook",
            content_id="wb-404",
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.NOT_FOUND

    def test_content_name_retornado(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """list_permissions retorna o nome do conteúdo no result."""
        client.get_permissions.return_value = []

        result = permissions.list_permissions(
            content_type="workbook",
            content_id="wb-1",
        )

        assert isinstance(result, PermissionsResult)
        assert result.content_name == "Test Content"

    def test_todos_content_types_aceitos(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """list_permissions aceita todos os PermContentType válidos."""
        client.get_permissions.return_value = []

        for ct in PermContentType:
            result = permissions.list_permissions(
                content_type=ct.value,
                content_id="id-1",
            )
            assert isinstance(result, PermissionsResult), f"Failed for {ct}"


# ==============================================================================
# list_default_permissions
# ==============================================================================


class TestListDefaultPermissions:
    """Testes para a ferramenta `list_default_permissions`."""

    def test_happy_path_retorna_default_permissions_result(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """Happy path retorna DefaultPermissionsResult."""
        rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow", "Write": "Allow"},
        )
        client.find_project_id.return_value = "proj-1"
        client.get_default_permissions.return_value = [rule]

        result = permissions.list_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
        )

        assert isinstance(result, DefaultPermissionsResult)
        assert result.status == "success"
        assert result.project_id == "proj-1"
        assert result.project_name == "Marketing"
        assert result.for_content_type == "workbook"
        assert len(result.permissions) == 1
        assert result.permissions[0].grantee_type == "user"
        assert result.permissions[0].grantee_id == "u-1"
        assert len(result.permissions[0].capabilities) == 2
        client.find_project_id.assert_called_once_with("Marketing")
        client.get_default_permissions.assert_called_once_with(
            "proj-1", PermContentType.workbook
        )

    def test_projeto_nao_encontrado_retorna_project_not_found(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """Projeto inexistente retorna ToolError(PROJECT_NOT_FOUND)."""
        client.find_project_id.return_value = None

        result = permissions.list_default_permissions(
            project_name="Fantasma",
            for_content_type="workbook",
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.PROJECT_NOT_FOUND
        assert "Fantasma" in result.error.message
        client.get_default_permissions.assert_not_called()

    def test_content_type_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """for_content_type inválido retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.list_default_permissions(
            project_name="Marketing",
            for_content_type="project",
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "project" in result.error.message
        session.assert_not_called()

    def test_content_type_view_invalido_para_default(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """for_content_type='view' retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.list_default_permissions(
            project_name="Marketing",
            for_content_type="view",
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "view" in result.error.message
        session.assert_not_called()

    def test_permissoes_vazias_retorna_lista_vazia(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """list_default_permissions sem regras retorna lista de permissions vazia."""
        client.find_project_id.return_value = "proj-1"
        client.get_default_permissions.return_value = []

        result = permissions.list_default_permissions(
            project_name="EmptyProject",
            for_content_type="datasource",
        )

        assert isinstance(result, DefaultPermissionsResult)
        assert result.permissions == []
        assert result.for_content_type == "datasource"

    def test_tableau_client_error_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """TableauClientError é convertido em ToolError."""
        client.find_project_id.return_value = "proj-1"
        client.get_default_permissions.side_effect = TableauClientError(
            ErrorCode.UPSTREAM_ERROR, "Erro na API REST."
        )

        result = permissions.list_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.UPSTREAM_ERROR

    def test_todos_content_types_validos_aceitos(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """Aceita workbook, datasource, flow, virtual_connection."""
        client.find_project_id.return_value = "proj-1"
        client.get_default_permissions.return_value = []

        valid_types = ["workbook", "datasource", "flow", "virtual_connection"]
        for ct in valid_types:
            result = permissions.list_default_permissions(
                project_name="Proj",
                for_content_type=ct,
            )
            assert isinstance(result, DefaultPermissionsResult), f"Failed for {ct}"
            assert result.for_content_type == ct

    def test_multiple_grantees_retornados(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """list_default_permissions retorna múltiplos grantees quando presentes."""
        rule_user = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )
        rule_group = _make_tsc_rule(
            grantee_type="group",
            grantee_id="g-1",
            grantee_name="Analysts",
            capabilities={"Write": "Allow", "ExportData": "Deny"},
        )
        client.find_project_id.return_value = "proj-1"
        client.get_default_permissions.return_value = [rule_user, rule_group]

        result = permissions.list_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
        )

        assert isinstance(result, DefaultPermissionsResult)
        assert len(result.permissions) == 2
        assert result.permissions[0].grantee_type == "user"
        assert result.permissions[1].grantee_type == "group"
        assert len(result.permissions[1].capabilities) == 2


# ==============================================================================
# set_default_permissions
# ==============================================================================


class TestSetDefaultPermissions:
    """Testes para a ferramenta `set_default_permissions`."""

    def test_happy_path_retorna_default_permissions_result(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """Happy path retorna DefaultPermissionsResult."""
        updated_rule = _make_tsc_rule(
            grantee_type="user",
            grantee_id="u-1",
            grantee_name="alice",
            capabilities={"Read": "Allow", "Write": "Allow"},
        )
        client.find_project_id.return_value = "proj-1"
        client.get_default_permissions.return_value = [updated_rule]

        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow", "Write": "Allow"},
        )

        assert isinstance(result, DefaultPermissionsResult)
        assert result.status == "success"
        assert result.project_id == "proj-1"
        assert result.project_name == "Marketing"
        assert result.for_content_type == "workbook"
        assert len(result.permissions) == 1
        assert result.permissions[0].grantee_type == "user"
        assert result.permissions[0].grantee_id == "u-1"
        client.find_project_id.assert_called_once_with("Marketing")
        client.resolve_user.assert_called_once_with("alice")
        client.update_default_permissions.assert_called_once()
        client.get_default_permissions.assert_called_once_with(
            "proj-1", PermContentType.workbook
        )

    def test_projeto_nao_encontrado_retorna_project_not_found(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """Projeto inexistente retorna ToolError(PROJECT_NOT_FOUND)."""
        client.find_project_id.return_value = None

        result = permissions.set_default_permissions(
            project_name="Fantasma",
            for_content_type="workbook",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.PROJECT_NOT_FOUND
        assert "Fantasma" in result.error.message
        client.resolve_user.assert_not_called()
        client.update_default_permissions.assert_not_called()

    def test_grantee_nao_encontrado_retorna_not_found(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """Grantee inexistente retorna ToolError(NOT_FOUND)."""
        client.find_project_id.return_value = "proj-1"
        client.resolve_user.side_effect = TableauClientError(
            ErrorCode.NOT_FOUND, "Usuário 'ghost' não encontrado no site."
        )

        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
            grantee_type="user",
            grantee_name="ghost",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.NOT_FOUND
        assert "ghost" in result.error.message
        client.update_default_permissions.assert_not_called()

    def test_content_type_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """for_content_type inválido retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="view",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "view" in result.error.message
        session.assert_not_called()

    def test_grantee_type_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """grantee_type inválido retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
            grantee_type="role",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "role" in result.error.message
        session.assert_not_called()

    def test_capabilities_vazio_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """capabilities vazio retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
            grantee_type="user",
            grantee_name="alice",
            capabilities={},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "vazio" in result.error.message
        session.assert_not_called()

    def test_capabilities_modo_invalido_retorna_validation_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """Modo inválido retorna ToolError(VALIDATION_ERROR)."""
        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Grant"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "Grant" in result.error.message
        session.assert_not_called()

    def test_com_grupo(self, client: MagicMock, session: MagicMock) -> None:
        """set_default_permissions com grantee_type='group' resolve grupo."""
        updated_rule = _make_tsc_rule(
            grantee_type="group",
            grantee_id="g-1",
            grantee_name="Analysts",
            capabilities={"Read": "Allow"},
        )
        client.find_project_id.return_value = "proj-1"
        client.resolve_group.return_value = ("g-1", 5)
        client.get_default_permissions.return_value = [updated_rule]

        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="datasource",
            grantee_type="group",
            grantee_name="Analysts",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, DefaultPermissionsResult)
        assert result.permissions[0].grantee_type == "group"
        assert result.permissions[0].grantee_id == "g-1"
        client.resolve_group.assert_called_once_with("Analysts")
        client.resolve_user.assert_not_called()

    def test_tableau_client_error_retorna_tool_error(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """TableauClientError é convertido em ToolError."""
        client.find_project_id.return_value = "proj-1"
        client.update_default_permissions.side_effect = TableauClientError(
            ErrorCode.UPSTREAM_ERROR, "Erro na API REST."
        )

        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="workbook",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.UPSTREAM_ERROR

    def test_flow_content_type_aceito(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """set_default_permissions aceita 'flow' como for_content_type."""
        client.find_project_id.return_value = "proj-1"
        client.get_default_permissions.return_value = []

        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="flow",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, DefaultPermissionsResult)
        assert result.for_content_type == "flow"
        client.update_default_permissions.assert_called_once()

    def test_virtual_connection_content_type_aceito(
        self, client: MagicMock, session: MagicMock
    ) -> None:
        """set_default_permissions aceita 'virtual_connection' como for_content_type."""
        client.find_project_id.return_value = "proj-1"
        client.get_default_permissions.return_value = []

        result = permissions.set_default_permissions(
            project_name="Marketing",
            for_content_type="virtual_connection",
            grantee_type="user",
            grantee_name="alice",
            capabilities={"Read": "Allow"},
        )

        assert isinstance(result, DefaultPermissionsResult)
        assert result.for_content_type == "virtual_connection"

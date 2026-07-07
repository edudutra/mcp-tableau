"""Testes unitários das tools de resolução de usuários/grupos (`tools/permissions.py`).

O `TableauClient` e a sessão (`tableau_session`/`load_settings`) são sempre
mockados no limite da integração — sem rede e sem Tableau real. Segue o padrão
de monkeypatch-at-tool-module já consolidado em `test_deploy.py`.
"""

from unittest.mock import MagicMock

import pytest

from mcp_tableau.models import (
    ErrorCode,
    GroupInfo,
    GroupListResult,
    GroupMembersResult,
    ResolveResult,
    ToolError,
    UserInfo,
    UserListResult,
)
from mcp_tableau.tableau.client import TableauClientError
from mcp_tableau.tools import permissions


@pytest.fixture
def client() -> MagicMock:
    """Mock do `TableauClient` com métodos de resolução de usuários/grupos."""
    mock = MagicMock(name="TableauClient")
    # Defaults: listas vazias / resolve retorna dados fictícios
    mock.list_users.return_value = []
    mock.list_groups.return_value = []
    mock.resolve_user.return_value = ("u-1", "Creator")
    mock.resolve_group.return_value = ("g-1", 5)
    mock.list_group_members.return_value = []
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

    def test_registra_cinco_ferramentas(self) -> None:
        mcp = MagicMock(name="FastMCP")

        permissions.register(mcp)

        assert mcp.tool.call_count == 5
        registered = [call.args[0] for call in mcp.tool.call_args_list]
        assert permissions.list_users in registered
        assert permissions.list_groups in registered
        assert permissions.resolve_user in registered
        assert permissions.resolve_group in registered
        assert permissions.list_group_members in registered


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

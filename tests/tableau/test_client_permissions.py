"""Testes unitários dos métodos de resolução de usuário/grupo e detecção de lock (Cap6).

Complementa `test_client.py` com cobertura dedicada para os 7 novos métodos do
`TableauClient` adicionados na task_02:
- resolve_user, list_users
- resolve_group, list_groups, list_group_members
- get_project_lock_state
- get_content_project_id
"""

from unittest.mock import MagicMock

import pytest
import tableauserverclient as TSC
from tableauserverclient.server.endpoint.exceptions import (
    ServerResponseError,
)

from mcp_tableau.config import Settings
from mcp_tableau.models import ErrorCode, PermContentType
from mcp_tableau.tableau.client import TableauClient, TableauClientError

# -- Fixtures reutilizáveis (padrão do projeto) --------------------------------


@pytest.fixture
def settings(tableau_env: dict[str, str]) -> Settings:
    """`Settings` construída a partir do ambiente de teste."""
    return Settings()  # type: ignore[call-arg]


@pytest.fixture
def server() -> MagicMock:
    """Mock do `TSC.Server` com sub-endpoints usados pelo cliente."""
    srv = MagicMock(name="Server")
    return srv


@pytest.fixture
def client(
    settings: Settings, server: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> TableauClient:
    """`TableauClient` cujo `TSC.Server` é substituído por um mock."""
    monkeypatch.setattr(TSC, "Server", lambda *a, **k: server)
    return TableauClient(settings)


def _server_error(http_status: int) -> ServerResponseError:
    """Constrói um `ServerResponseError` com código que embute o status HTTP."""
    return ServerResponseError(
        code=f"{http_status}003", summary="erro", detail="detalhe"
    )


# ==============================================================================
# resolve_user
# ==============================================================================


class TestResolveUser:
    """Testes para `TableauClient.resolve_user`."""

    def test_resolve_user_existente_retorna_luid_e_site_role(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        user = MagicMock(id="user-luid-1", site_role="Creator")
        server.users.get.return_value = ([user], MagicMock())

        luid, site_role = client.resolve_user("alice")

        assert luid == "user-luid-1"
        assert site_role == "Creator"
        # Verifica que o filtro server-side foi usado
        req_options = server.users.get.call_args.args[0]
        assert isinstance(req_options, TSC.RequestOptions)

    def test_resolve_user_inexistente_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        server.users.get.return_value = ([], MagicMock())

        with pytest.raises(TableauClientError) as exc_info:
            client.resolve_user("nonexistent")

        assert exc_info.value.code is ErrorCode.NOT_FOUND
        assert "nonexistent" in exc_info.value.message

    def test_resolve_user_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        user = MagicMock(id="u-1", site_role="Viewer")
        server.users.get.side_effect = [
            _server_error(401),
            ([user], MagicMock()),
        ]

        luid, site_role = client.resolve_user("bob")

        assert luid == "u-1"
        assert site_role == "Viewer"
        server.auth.sign_in.assert_called_once()
        assert server.users.get.call_count == 2

    def test_resolve_user_site_role_none_retorna_string_vazia(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        user = MagicMock(id="u-1", site_role=None)
        server.users.get.return_value = ([user], MagicMock())

        _, site_role = client.resolve_user("charlie")

        assert site_role == ""


# ==============================================================================
# list_users
# ==============================================================================


class TestListUsers:
    """Testes para `TableauClient.list_users`."""

    def test_list_users_sem_filtro_retorna_todos(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        u1 = MagicMock(id="u-1", site_role="Creator")
        u1.name = "alice"
        u2 = MagicMock(id="u-2", site_role="Viewer")
        u2.name = "bob"

        monkeypatch.setattr(TSC, "Pager", lambda endpoint, *a, **k: iter([u1, u2]))

        result = client.list_users()

        assert len(result) == 2
        assert result[0] == ("u-1", "alice", "Creator")
        assert result[1] == ("u-2", "bob", "Viewer")

    def test_list_users_com_name_filter_aplica_filtro(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        u1 = MagicMock(id="u-1", site_role="Creator")
        u1.name = "alice"

        # Capture the request options passed to Pager
        captured_opts: list[TSC.RequestOptions] = []

        def fake_pager(endpoint, req_options=None, *a, **k):  # type: ignore[no-untyped-def]
            if req_options is not None:
                captured_opts.append(req_options)
            return iter([u1])

        monkeypatch.setattr(TSC, "Pager", fake_pager)

        result = client.list_users(name_filter="alice")

        assert len(result) == 1
        assert result[0] == ("u-1", "alice", "Creator")
        # Verify filter was applied
        assert len(captured_opts) == 1
        assert len(captured_opts[0].filter) == 1

    def test_list_users_reautentica_em_401(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        u1 = MagicMock(id="u-1", site_role="Viewer")
        u1.name = "alice"

        call_count = {"n": 0}

        def fake_pager(endpoint, *a, **k):  # type: ignore[no-untyped-def]
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise _server_error(401)
            return iter([u1])

        monkeypatch.setattr(TSC, "Pager", fake_pager)

        result = client.list_users()

        assert result == [("u-1", "alice", "Viewer")]
        server.auth.sign_in.assert_called_once()


# ==============================================================================
# resolve_group
# ==============================================================================


class TestResolveGroup:
    """Testes para `TableauClient.resolve_group`."""

    def test_resolve_group_existente_retorna_luid_e_user_count(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        group = MagicMock(id="g-luid-1", user_count=5)
        server.groups.get.return_value = ([group], MagicMock())

        luid, user_count = client.resolve_group("developers")

        assert luid == "g-luid-1"
        assert user_count == 5

    def test_resolve_group_inexistente_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        server.groups.get.return_value = ([], MagicMock())

        with pytest.raises(TableauClientError) as exc_info:
            client.resolve_group("ghost-group")

        assert exc_info.value.code is ErrorCode.NOT_FOUND
        assert "ghost-group" in exc_info.value.message

    def test_resolve_group_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        group = MagicMock(id="g-1", user_count=3)
        server.groups.get.side_effect = [
            _server_error(401),
            ([group], MagicMock()),
        ]

        luid, user_count = client.resolve_group("admins")

        assert luid == "g-1"
        assert user_count == 3
        server.auth.sign_in.assert_called_once()

    def test_resolve_group_sem_user_count_retorna_none(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        group = MagicMock(id="g-1", spec=[])
        group.id = "g-1"
        # Simulate group without user_count attribute
        server.groups.get.return_value = ([group], MagicMock())

        luid, user_count = client.resolve_group("empty-group")

        assert luid == "g-1"
        assert user_count is None


# ==============================================================================
# list_groups
# ==============================================================================


class TestListGroups:
    """Testes para `TableauClient.list_groups`."""

    def test_list_groups_sem_filtro_retorna_todos(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        g1 = MagicMock(id="g-1", user_count=5)
        g1.name = "developers"
        g2 = MagicMock(id="g-2", user_count=10)
        g2.name = "admins"

        monkeypatch.setattr(TSC, "Pager", lambda endpoint, *a, **k: iter([g1, g2]))

        result = client.list_groups()

        assert len(result) == 2
        assert result[0] == ("g-1", "developers", 5)
        assert result[1] == ("g-2", "admins", 10)

    def test_list_groups_com_name_filter_aplica_filtro(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        g1 = MagicMock(id="g-1", user_count=5)
        g1.name = "developers"

        captured_opts: list[TSC.RequestOptions] = []

        def fake_pager(endpoint, req_options=None, *a, **k):  # type: ignore[no-untyped-def]
            if req_options is not None:
                captured_opts.append(req_options)
            return iter([g1])

        monkeypatch.setattr(TSC, "Pager", fake_pager)

        result = client.list_groups(name_filter="developers")

        assert len(result) == 1
        assert result[0] == ("g-1", "developers", 5)
        assert len(captured_opts) == 1
        assert len(captured_opts[0].filter) == 1

    def test_list_groups_reautentica_em_401(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        g1 = MagicMock(id="g-1", user_count=2)
        g1.name = "team"

        call_count = {"n": 0}

        def fake_pager(endpoint, *a, **k):  # type: ignore[no-untyped-def]
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise _server_error(401)
            return iter([g1])

        monkeypatch.setattr(TSC, "Pager", fake_pager)

        result = client.list_groups()

        assert result == [("g-1", "team", 2)]
        server.auth.sign_in.assert_called_once()


# ==============================================================================
# list_group_members
# ==============================================================================


class TestListGroupMembers:
    """Testes para `TableauClient.list_group_members`."""

    def test_list_group_members_retorna_lista_de_membros(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        u1 = MagicMock(id="u-1", site_role="Creator")
        u1.name = "alice"
        u2 = MagicMock(id="u-2", site_role="Viewer")
        u2.name = "bob"

        monkeypatch.setattr(TSC, "Pager", lambda endpoint, *a, **k: iter([u1, u2]))

        result = client.list_group_members("g-1")

        assert len(result) == 2
        assert result[0] == ("u-1", "alice", "Creator")
        assert result[1] == ("u-2", "bob", "Viewer")

    def test_list_group_members_grupo_vazio_retorna_lista_vazia(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(TSC, "Pager", lambda endpoint, *a, **k: iter([]))

        result = client.list_group_members("g-empty")

        assert result == []

    def test_list_group_members_reautentica_em_401(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        u1 = MagicMock(id="u-1", site_role="Creator")
        u1.name = "alice"

        call_count = {"n": 0}

        def fake_pager(endpoint, *a, **k):  # type: ignore[no-untyped-def]
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise _server_error(401)
            return iter([u1])

        monkeypatch.setattr(TSC, "Pager", fake_pager)

        result = client.list_group_members("g-1")

        assert result == [("u-1", "alice", "Creator")]
        server.auth.sign_in.assert_called_once()

    def test_list_group_members_404_levanta_not_found(
        self, client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_pager(endpoint, *a, **k):  # type: ignore[no-untyped-def]
            raise _server_error(404)

        monkeypatch.setattr(TSC, "Pager", fake_pager)

        with pytest.raises(TableauClientError) as exc_info:
            client.list_group_members("missing-group")

        assert exc_info.value.code is ErrorCode.NOT_FOUND


# ==============================================================================
# get_project_lock_state
# ==============================================================================


class TestGetProjectLockState:
    """Testes para `TableauClient.get_project_lock_state`."""

    def test_projeto_desbloqueado_retorna_managed_by_owner(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        project = MagicMock(content_permissions="ManagedByOwner")
        server.projects.get_by_id.return_value = project

        result = client.get_project_lock_state("p-1")

        assert result == "ManagedByOwner"
        server.projects.get_by_id.assert_called_once_with("p-1")

    def test_projeto_bloqueado_retorna_locked_to_project(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        project = MagicMock(content_permissions="LockedToProject")
        server.projects.get_by_id.return_value = project

        result = client.get_project_lock_state("p-2")

        assert result == "LockedToProject"

    def test_projeto_bloqueado_sem_nested_retorna_locked_without_nested(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        project = MagicMock(content_permissions="LockedToProjectWithoutNested")
        server.projects.get_by_id.return_value = project

        result = client.get_project_lock_state("p-3")

        assert result == "LockedToProjectWithoutNested"

    def test_content_permissions_none_retorna_managed_by_owner(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        project = MagicMock(content_permissions=None)
        server.projects.get_by_id.return_value = project

        result = client.get_project_lock_state("p-4")

        assert result == "ManagedByOwner"

    def test_get_project_lock_state_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        project = MagicMock(content_permissions="ManagedByOwner")
        server.projects.get_by_id.side_effect = [
            _server_error(401),
            project,
        ]

        result = client.get_project_lock_state("p-1")

        assert result == "ManagedByOwner"
        server.auth.sign_in.assert_called_once()
        assert server.projects.get_by_id.call_count == 2

    def test_get_project_lock_state_404_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        server.projects.get_by_id.side_effect = _server_error(404)

        with pytest.raises(TableauClientError) as exc_info:
            client.get_project_lock_state("missing")

        assert exc_info.value.code is ErrorCode.NOT_FOUND


# ==============================================================================
# get_content_project_id
# ==============================================================================


class TestGetContentProjectId:
    """Testes para `TableauClient.get_content_project_id`."""

    def test_project_retorna_proprio_id(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        # Para projeto, retorna o próprio content_id sem chamada à API
        result = client.get_content_project_id(PermContentType.project, "p-1")

        assert result == "p-1"
        # Nenhum get_by_id deve ter sido chamado
        server.workbooks.get_by_id.assert_not_called()
        server.datasources.get_by_id.assert_not_called()
        server.projects.get_by_id.assert_not_called()

    def test_workbook_retorna_project_id_do_workbook(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        wb = MagicMock(project_id="p-wb")
        server.workbooks.get_by_id.return_value = wb

        result = client.get_content_project_id(PermContentType.workbook, "wb-1")

        assert result == "p-wb"
        server.workbooks.get_by_id.assert_called_once_with("wb-1")

    def test_datasource_retorna_project_id_do_datasource(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        ds = MagicMock(project_id="p-ds")
        server.datasources.get_by_id.return_value = ds

        result = client.get_content_project_id(PermContentType.datasource, "ds-1")

        assert result == "p-ds"
        server.datasources.get_by_id.assert_called_once_with("ds-1")

    def test_view_retorna_project_id_da_view(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        view = MagicMock(project_id="p-view")
        server.views.get_by_id.return_value = view

        result = client.get_content_project_id(PermContentType.view, "v-1")

        assert result == "p-view"
        server.views.get_by_id.assert_called_once_with("v-1")

    def test_flow_retorna_project_id_do_flow(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        flow = MagicMock(project_id="p-flow")
        server.flows.get_by_id.return_value = flow

        result = client.get_content_project_id(PermContentType.flow, "fl-1")

        assert result == "p-flow"
        server.flows.get_by_id.assert_called_once_with("fl-1")

    def test_virtual_connection_retorna_project_id(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        vc = MagicMock(project_id="p-vc")
        server.virtual_connections.get_by_id.return_value = vc

        result = client.get_content_project_id(
            PermContentType.virtual_connection, "vc-1"
        )

        assert result == "p-vc"
        server.virtual_connections.get_by_id.assert_called_once_with("vc-1")

    def test_item_sem_project_id_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        wb = MagicMock(project_id=None)
        server.workbooks.get_by_id.return_value = wb

        with pytest.raises(TableauClientError) as exc_info:
            client.get_content_project_id(PermContentType.workbook, "wb-broken")

        assert exc_info.value.code is ErrorCode.NOT_FOUND

    def test_item_com_project_id_vazio_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        wb = MagicMock(project_id="")
        server.workbooks.get_by_id.return_value = wb

        with pytest.raises(TableauClientError) as exc_info:
            client.get_content_project_id(PermContentType.workbook, "wb-empty")

        assert exc_info.value.code is ErrorCode.NOT_FOUND

    def test_get_content_project_id_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        wb = MagicMock(project_id="p-1")
        server.workbooks.get_by_id.side_effect = [
            _server_error(401),
            wb,
        ]

        result = client.get_content_project_id(PermContentType.workbook, "wb-1")

        assert result == "p-1"
        server.auth.sign_in.assert_called_once()
        assert server.workbooks.get_by_id.call_count == 2

    def test_get_content_project_id_404_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        server.datasources.get_by_id.side_effect = _server_error(404)

        with pytest.raises(TableauClientError) as exc_info:
            client.get_content_project_id(PermContentType.datasource, "missing")

        assert exc_info.value.code is ErrorCode.NOT_FOUND

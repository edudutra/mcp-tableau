"""Testes unitários dos métodos de dispatch de permissões do TableauClient (Cap6).

Cobre os 5 novos métodos adicionados na task_03:
- get_permissions (dispatch para 6 content types)
- update_permissions (dispatch + assimetria virtual_connection)
- delete_permission (dispatch)
- get_default_permissions (project defaults por content type)
- update_default_permissions (project defaults por content type)

Também testa:
- _validate_content_type (validação de enum inválido)
- _check_view_show_tabs (detecção de showTabs no workbook pai)
- Reautenticação em 401 via _with_reauth
"""

from unittest.mock import MagicMock

import pytest
import tableauserverclient as TSC
from tableauserverclient.server.endpoint.exceptions import ServerResponseError

from mcp_tableau.config import Settings
from mcp_tableau.models import ErrorCode, PermContentType
from mcp_tableau.tableau.client import TableauClient, TableauClientError

# -- Fixtures reutilizáveis ----------------------------------------------------


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


def _mock_item(
    permissions: list | None = None,
    project_id: str = "p-1",
    workbook_id: str | None = None,
    show_tabs: bool = False,
) -> MagicMock:
    """Cria um mock de item TSC com permissions populáveis."""
    item = MagicMock()
    item.project_id = project_id
    item.id = "item-1"
    item.workbook_id = workbook_id
    item.show_tabs = show_tabs
    # permissions é uma property que chama o fetcher. Simula o populate.
    item.permissions = permissions if permissions is not None else []
    return item


# ==============================================================================
# get_permissions
# ==============================================================================


class TestGetPermissions:
    """Testes para `TableauClient.get_permissions`."""

    def test_workbook_dispatch_popula_e_retorna_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        item = _mock_item(permissions=rules)
        server.workbooks.get_by_id.return_value = item
        server.workbooks.populate_permissions.return_value = None

        result = client.get_permissions(PermContentType.workbook, "wb-1")

        assert result == rules
        server.workbooks.get_by_id.assert_called_once_with("wb-1")
        server.workbooks.populate_permissions.assert_called_once_with(item)

    def test_datasource_dispatch_popula_e_retorna_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1"), MagicMock(name="rule2")]
        item = _mock_item(permissions=rules)
        server.datasources.get_by_id.return_value = item
        server.datasources.populate_permissions.return_value = None

        result = client.get_permissions(PermContentType.datasource, "ds-1")

        assert result == rules
        server.datasources.get_by_id.assert_called_once_with("ds-1")
        server.datasources.populate_permissions.assert_called_once_with(item)

    def test_project_dispatch_popula_e_retorna_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        item = _mock_item(permissions=rules)
        server.projects.get_by_id.return_value = item
        server.projects.populate_permissions.return_value = None

        result = client.get_permissions(PermContentType.project, "p-1")

        assert result == rules
        server.projects.get_by_id.assert_called_once_with("p-1")
        server.projects.populate_permissions.assert_called_once_with(item)

    def test_view_dispatch_popula_e_retorna_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        item = _mock_item(permissions=rules)
        server.views.get_by_id.return_value = item
        server.views.populate_permissions.return_value = None

        result = client.get_permissions(PermContentType.view, "v-1")

        assert result == rules
        server.views.get_by_id.assert_called_once_with("v-1")
        server.views.populate_permissions.assert_called_once_with(item)

    def test_flow_dispatch_popula_e_retorna_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        item = _mock_item(permissions=rules)
        server.flows.get_by_id.return_value = item
        server.flows.populate_permissions.return_value = None

        result = client.get_permissions(PermContentType.flow, "fl-1")

        assert result == rules
        server.flows.get_by_id.assert_called_once_with("fl-1")
        server.flows.populate_permissions.assert_called_once_with(item)

    def test_virtual_connection_dispatch_popula_e_retorna_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        item = _mock_item(permissions=rules)
        server.virtual_connections.get_by_id.return_value = item
        server.virtual_connections.populate_permissions.return_value = None

        result = client.get_permissions(PermContentType.virtual_connection, "vc-1")

        assert result == rules
        server.virtual_connections.get_by_id.assert_called_once_with("vc-1")
        server.virtual_connections.populate_permissions.assert_called_once_with(item)

    def test_get_permissions_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        item = _mock_item(permissions=rules)
        # Primeiro call levanta 401, segundo funciona
        server.workbooks.get_by_id.side_effect = [
            _server_error(401),
            item,
        ]
        server.workbooks.populate_permissions.return_value = None

        result = client.get_permissions(PermContentType.workbook, "wb-1")

        assert result == rules
        server.auth.sign_in.assert_called_once()
        assert server.workbooks.get_by_id.call_count == 2

    def test_get_permissions_404_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        server.workbooks.get_by_id.side_effect = _server_error(404)

        with pytest.raises(TableauClientError) as exc_info:
            client.get_permissions(PermContentType.workbook, "missing")

        assert exc_info.value.code is ErrorCode.NOT_FOUND


# ==============================================================================
# update_permissions
# ==============================================================================


class TestUpdatePermissions:
    """Testes para `TableauClient.update_permissions`."""

    def test_workbook_update_permissions_usa_update_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        item = _mock_item()
        server.workbooks.get_by_id.return_value = item
        server.workbooks.update_permissions.return_value = updated_rules

        result = client.update_permissions(PermContentType.workbook, "wb-1", rules)

        assert result == updated_rules
        server.workbooks.get_by_id.assert_called_once_with("wb-1")
        server.workbooks.update_permissions.assert_called_once_with(item, rules)

    def test_datasource_update_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        item = _mock_item()
        server.datasources.get_by_id.return_value = item
        server.datasources.update_permissions.return_value = updated_rules

        result = client.update_permissions(PermContentType.datasource, "ds-1", rules)

        assert result == updated_rules
        server.datasources.update_permissions.assert_called_once_with(item, rules)

    def test_project_update_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        item = _mock_item()
        server.projects.get_by_id.return_value = item
        server.projects.update_permissions.return_value = updated_rules

        result = client.update_permissions(PermContentType.project, "p-1", rules)

        assert result == updated_rules
        server.projects.update_permissions.assert_called_once_with(item, rules)

    def test_flow_update_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        item = _mock_item()
        server.flows.get_by_id.return_value = item
        server.flows.update_permissions.return_value = updated_rules

        result = client.update_permissions(PermContentType.flow, "fl-1", rules)

        assert result == updated_rules
        server.flows.update_permissions.assert_called_once_with(item, rules)

    def test_virtual_connection_usa_add_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """virtual_connection usa `add_permissions` em vez de `update_permissions`."""
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        item = _mock_item()
        server.virtual_connections.get_by_id.return_value = item
        server.virtual_connections.add_permissions.return_value = updated_rules

        result = client.update_permissions(
            PermContentType.virtual_connection, "vc-1", rules
        )

        assert result == updated_rules
        server.virtual_connections.add_permissions.assert_called_once_with(item, rules)
        # update_permissions NÃO deve ser chamado
        server.virtual_connections.update_permissions.assert_not_called()

    def test_view_com_show_tabs_levanta_erro(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """View com workbook pai showTabs=True levanta SHOW_TABS_ENABLED."""
        rules = [MagicMock(name="rule1")]
        view_item = _mock_item(workbook_id="wb-parent")
        wb_item = MagicMock(show_tabs=True)
        server.views.get_by_id.return_value = view_item
        server.workbooks.get_by_id.return_value = wb_item

        with pytest.raises(TableauClientError) as exc_info:
            client.update_permissions(PermContentType.view, "v-1", rules)

        assert exc_info.value.code is ErrorCode.SHOW_TABS_ENABLED
        assert "showTabs" in exc_info.value.message

    def test_view_sem_show_tabs_funciona_normalmente(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """View com showTabs=False permite update normalmente."""
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        view_item = _mock_item(workbook_id="wb-parent")
        wb_item = MagicMock(show_tabs=False)
        server.views.get_by_id.return_value = view_item
        server.workbooks.get_by_id.return_value = wb_item
        server.views.update_permissions.return_value = updated_rules

        result = client.update_permissions(PermContentType.view, "v-1", rules)

        assert result == updated_rules

    def test_view_sem_workbook_id_permite_update(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """View sem workbook_id pula a verificação de showTabs."""
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        view_item = _mock_item(workbook_id=None)
        server.views.get_by_id.return_value = view_item
        server.views.update_permissions.return_value = updated_rules

        result = client.update_permissions(PermContentType.view, "v-1", rules)

        assert result == updated_rules
        # Não deve tentar buscar workbook
        server.workbooks.get_by_id.assert_not_called()

    def test_update_permissions_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        item = _mock_item()
        server.datasources.get_by_id.side_effect = [
            _server_error(401),
            item,
        ]
        server.datasources.update_permissions.return_value = updated_rules

        result = client.update_permissions(PermContentType.datasource, "ds-1", rules)

        assert result == updated_rules
        server.auth.sign_in.assert_called_once()


# ==============================================================================
# delete_permission
# ==============================================================================


class TestDeletePermission:
    """Testes para `TableauClient.delete_permission`."""

    def test_workbook_delete_permission(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rule = MagicMock(name="rule_to_delete")
        item = _mock_item()
        server.workbooks.get_by_id.return_value = item
        server.workbooks.delete_permission.return_value = None

        client.delete_permission(PermContentType.workbook, "wb-1", rule)

        server.workbooks.get_by_id.assert_called_once_with("wb-1")
        server.workbooks.delete_permission.assert_called_once_with(item, rule)

    def test_datasource_delete_permission(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rule = MagicMock(name="rule_to_delete")
        item = _mock_item()
        server.datasources.get_by_id.return_value = item
        server.datasources.delete_permission.return_value = None

        client.delete_permission(PermContentType.datasource, "ds-1", rule)

        server.datasources.delete_permission.assert_called_once_with(item, rule)

    def test_project_delete_permission(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rule = MagicMock(name="rule_to_delete")
        item = _mock_item()
        server.projects.get_by_id.return_value = item
        server.projects.delete_permission.return_value = None

        client.delete_permission(PermContentType.project, "p-1", rule)

        server.projects.delete_permission.assert_called_once_with(item, rule)

    def test_flow_delete_permission(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rule = MagicMock(name="rule_to_delete")
        item = _mock_item()
        server.flows.get_by_id.return_value = item
        server.flows.delete_permission.return_value = None

        client.delete_permission(PermContentType.flow, "fl-1", rule)

        server.flows.delete_permission.assert_called_once_with(item, rule)

    def test_virtual_connection_delete_permission(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rule = MagicMock(name="rule_to_delete")
        item = _mock_item()
        server.virtual_connections.get_by_id.return_value = item
        server.virtual_connections.delete_permission.return_value = None

        client.delete_permission(PermContentType.virtual_connection, "vc-1", rule)

        server.virtual_connections.delete_permission.assert_called_once_with(item, rule)

    def test_view_com_show_tabs_levanta_erro_ao_deletar(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """View com workbook pai showTabs=True levanta SHOW_TABS_ENABLED."""
        rule = MagicMock(name="rule_to_delete")
        view_item = _mock_item(workbook_id="wb-parent")
        wb_item = MagicMock(show_tabs=True)
        server.views.get_by_id.return_value = view_item
        server.workbooks.get_by_id.return_value = wb_item

        with pytest.raises(TableauClientError) as exc_info:
            client.delete_permission(PermContentType.view, "v-1", rule)

        assert exc_info.value.code is ErrorCode.SHOW_TABS_ENABLED

    def test_delete_permission_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rule = MagicMock(name="rule_to_delete")
        item = _mock_item()
        server.workbooks.get_by_id.side_effect = [
            _server_error(401),
            item,
        ]
        server.workbooks.delete_permission.return_value = None

        client.delete_permission(PermContentType.workbook, "wb-1", rule)

        server.auth.sign_in.assert_called_once()
        assert server.workbooks.get_by_id.call_count == 2

    def test_delete_permission_404_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rule = MagicMock(name="rule_to_delete")
        server.datasources.get_by_id.side_effect = _server_error(404)

        with pytest.raises(TableauClientError) as exc_info:
            client.delete_permission(PermContentType.datasource, "missing", rule)

        assert exc_info.value.code is ErrorCode.NOT_FOUND


# ==============================================================================
# get_default_permissions
# ==============================================================================


class TestGetDefaultPermissions:
    """Testes para `TableauClient.get_default_permissions`."""

    def test_workbook_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="default_rule")]
        project = MagicMock()
        project.id = "p-1"
        # Simula o atributo dinâmico criado por _set_default_permissions
        project._default_workbook_permissions = lambda: rules
        server.projects.get_by_id.return_value = project
        dp = server.projects._default_permissions
        dp.populate_default_permissions.return_value = None

        result = client.get_default_permissions("p-1", PermContentType.workbook)

        assert result == rules
        server.projects.get_by_id.assert_called_once_with("p-1")
        dp.populate_default_permissions.assert_called_once_with(project, "workbook")

    def test_datasource_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="default_rule")]
        project = MagicMock()
        project.id = "p-1"
        project._default_datasource_permissions = lambda: rules
        server.projects.get_by_id.return_value = project
        dp = server.projects._default_permissions
        dp.populate_default_permissions.return_value = None

        result = client.get_default_permissions("p-1", PermContentType.datasource)

        assert result == rules
        dp.populate_default_permissions.assert_called_once_with(project, "datasource")

    def test_flow_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="default_rule")]
        project = MagicMock()
        project.id = "p-1"
        project._default_flow_permissions = lambda: rules
        server.projects.get_by_id.return_value = project
        dp = server.projects._default_permissions
        dp.populate_default_permissions.return_value = None

        result = client.get_default_permissions("p-1", PermContentType.flow)

        assert result == rules
        dp.populate_default_permissions.assert_called_once_with(project, "flow")

    def test_virtual_connection_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="default_rule")]
        project = MagicMock()
        project.id = "p-1"
        project._default_virtualconnection_permissions = lambda: rules
        server.projects.get_by_id.return_value = project
        dp = server.projects._default_permissions
        dp.populate_default_permissions.return_value = None

        result = client.get_default_permissions(
            "p-1", PermContentType.virtual_connection
        )

        assert result == rules
        dp.populate_default_permissions.assert_called_once_with(
            project, "virtualConnection"
        )

    def test_project_tipo_invalido_para_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """project não tem default permissions — levanta VALIDATION_ERROR."""
        with pytest.raises(TableauClientError) as exc_info:
            client.get_default_permissions("p-1", PermContentType.project)

        assert exc_info.value.code is ErrorCode.VALIDATION_ERROR
        assert "project" in exc_info.value.message

    def test_view_tipo_invalido_para_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """view não tem default permissions — levanta VALIDATION_ERROR."""
        with pytest.raises(TableauClientError) as exc_info:
            client.get_default_permissions("p-1", PermContentType.view)

        assert exc_info.value.code is ErrorCode.VALIDATION_ERROR

    def test_get_default_permissions_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="default_rule")]
        project = MagicMock()
        project.id = "p-1"
        project._default_workbook_permissions = lambda: rules
        server.projects.get_by_id.side_effect = [
            _server_error(401),
            project,
        ]
        dp = server.projects._default_permissions
        dp.populate_default_permissions.return_value = None

        result = client.get_default_permissions("p-1", PermContentType.workbook)

        assert result == rules
        server.auth.sign_in.assert_called_once()

    def test_get_default_permissions_atributo_ausente_retorna_lista_vazia(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """Se o atributo dinâmico não existir, retorna lista vazia."""
        project = MagicMock(spec=[])
        project.id = "p-1"
        # MagicMock com spec=[] não terá _default_workbook_permissions
        server.projects.get_by_id.return_value = project
        dp = server.projects._default_permissions
        dp.populate_default_permissions.return_value = None

        result = client.get_default_permissions("p-1", PermContentType.workbook)

        assert result == []


# ==============================================================================
# update_default_permissions
# ==============================================================================


class TestUpdateDefaultPermissions:
    """Testes para `TableauClient.update_default_permissions`."""

    def test_workbook_update_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        project = MagicMock()
        project.id = "p-1"
        server.projects.get_by_id.return_value = project
        server.projects._default_permissions.update_default_permissions.return_value = (
            updated_rules
        )

        result = client.update_default_permissions(
            "p-1", PermContentType.workbook, rules
        )

        assert result == updated_rules
        server.projects.get_by_id.assert_called_once_with("p-1")
        server.projects._default_permissions.update_default_permissions.assert_called_once_with(
            project, rules, "workbook"
        )

    def test_datasource_update_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        project = MagicMock()
        project.id = "p-1"
        server.projects.get_by_id.return_value = project
        server.projects._default_permissions.update_default_permissions.return_value = (
            updated_rules
        )

        result = client.update_default_permissions(
            "p-1", PermContentType.datasource, rules
        )

        assert result == updated_rules
        server.projects._default_permissions.update_default_permissions.assert_called_once_with(
            project, rules, "datasource"
        )

    def test_flow_update_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        project = MagicMock()
        project.id = "p-1"
        server.projects.get_by_id.return_value = project
        server.projects._default_permissions.update_default_permissions.return_value = (
            updated_rules
        )

        result = client.update_default_permissions("p-1", PermContentType.flow, rules)

        assert result == updated_rules
        server.projects._default_permissions.update_default_permissions.assert_called_once_with(
            project, rules, "flow"
        )

    def test_virtual_connection_update_default_permissions(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        project = MagicMock()
        project.id = "p-1"
        server.projects.get_by_id.return_value = project
        server.projects._default_permissions.update_default_permissions.return_value = (
            updated_rules
        )

        result = client.update_default_permissions(
            "p-1", PermContentType.virtual_connection, rules
        )

        assert result == updated_rules
        server.projects._default_permissions.update_default_permissions.assert_called_once_with(
            project, rules, "virtualConnection"
        )

    def test_project_tipo_invalido_levanta_validation_error(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]

        with pytest.raises(TableauClientError) as exc_info:
            client.update_default_permissions("p-1", PermContentType.project, rules)

        assert exc_info.value.code is ErrorCode.VALIDATION_ERROR

    def test_view_tipo_invalido_levanta_validation_error(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]

        with pytest.raises(TableauClientError) as exc_info:
            client.update_default_permissions("p-1", PermContentType.view, rules)

        assert exc_info.value.code is ErrorCode.VALIDATION_ERROR

    def test_update_default_permissions_reautentica_em_401(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        updated_rules = [MagicMock(name="updated")]
        project = MagicMock()
        project.id = "p-1"
        server.projects.get_by_id.side_effect = [
            _server_error(401),
            project,
        ]
        server.projects._default_permissions.update_default_permissions.return_value = (
            updated_rules
        )

        result = client.update_default_permissions(
            "p-1", PermContentType.workbook, rules
        )

        assert result == updated_rules
        server.auth.sign_in.assert_called_once()

    def test_update_default_permissions_404_levanta_not_found(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        rules = [MagicMock(name="rule1")]
        server.projects.get_by_id.side_effect = _server_error(404)

        with pytest.raises(TableauClientError) as exc_info:
            client.update_default_permissions(
                "missing", PermContentType.workbook, rules
            )

        assert exc_info.value.code is ErrorCode.NOT_FOUND


# ==============================================================================
# _validate_content_type
# ==============================================================================


class TestValidateContentType:
    """Testes para `TableauClient._validate_content_type`."""

    def test_todos_os_tipos_validos_passam(self, client: TableauClient) -> None:
        for ct in PermContentType:
            # Não deve levantar exceção
            client._validate_content_type(ct)

    def test_tipo_invalido_levanta_validation_error(
        self, client: TableauClient
    ) -> None:
        """String que não é membro do enum — simula uso incorreto."""
        # Forçamos um valor inválido contornando o enum
        with pytest.raises(TableauClientError) as exc_info:
            client._validate_content_type("invalid_type")  # type: ignore[arg-type]

        assert exc_info.value.code is ErrorCode.VALIDATION_ERROR


# ==============================================================================
# _check_view_show_tabs
# ==============================================================================


class TestCheckViewShowTabs:
    """Testes para `TableauClient._check_view_show_tabs`."""

    def test_nao_view_nao_verifica(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """Tipos que não são view não passam pela verificação."""
        item = _mock_item(workbook_id="wb-1")
        # Não deve chamar workbooks.get_by_id
        client._check_view_show_tabs(PermContentType.workbook, item)
        server.workbooks.get_by_id.assert_not_called()

    def test_view_sem_workbook_id_nao_verifica(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        """View sem workbook_id não tenta buscar workbook."""
        item = _mock_item(workbook_id=None)
        client._check_view_show_tabs(PermContentType.view, item)
        server.workbooks.get_by_id.assert_not_called()

    def test_view_com_show_tabs_true_levanta_erro(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        item = _mock_item(workbook_id="wb-parent")
        wb = MagicMock(show_tabs=True)
        server.workbooks.get_by_id.return_value = wb

        with pytest.raises(TableauClientError) as exc_info:
            client._check_view_show_tabs(PermContentType.view, item)

        assert exc_info.value.code is ErrorCode.SHOW_TABS_ENABLED

    def test_view_com_show_tabs_false_nao_levanta(
        self, client: TableauClient, server: MagicMock
    ) -> None:
        item = _mock_item(workbook_id="wb-parent")
        wb = MagicMock(show_tabs=False)
        server.workbooks.get_by_id.return_value = wb

        # Não deve levantar exceção
        client._check_view_show_tabs(PermContentType.view, item)

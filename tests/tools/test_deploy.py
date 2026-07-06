"""Testes unitários das tools de deploy (`tools/deploy.py`).

O `TableauClient` e a sessão (`tableau_session`/`load_settings`) são sempre
mockados no limite da integração — sem rede e sem Tableau real. A validação
local (extensão/existência) deve ocorrer **antes** de qualquer uso do client.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_tableau.models import ContentRef, ErrorCode, PublishResult, ToolError
from mcp_tableau.tableau.client import PublishedRef, TableauClientError
from mcp_tableau.tools import deploy


@pytest.fixture
def client() -> MagicMock:
    """Mock do `TableauClient` com os métodos consumidos pelas tools de deploy."""
    mock = MagicMock(name="TableauClient")
    mock.find_project_id.return_value = "p-1"
    mock.search_content.return_value = []
    return mock


@pytest.fixture
def session(client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Monkeypatcha `tableau_session`/`load_settings` no módulo `deploy`.

    `tableau_session` vira um context manager que produz o `client` mock; a
    `load_settings` retorna um `MagicMock`. Retorna o mock de `tableau_session`
    para asserts de "não chamou o client".
    """
    session_cm = MagicMock(name="tableau_session")
    session_cm.return_value.__enter__.return_value = client
    session_cm.return_value.__exit__.return_value = False
    monkeypatch.setattr(deploy, "tableau_session", session_cm)
    monkeypatch.setattr(deploy, "load_settings", MagicMock(return_value=MagicMock()))
    return session_cm


def _workbook(tmp_path: Path, name: str = "Vendas", suffix: str = ".twbx") -> Path:
    """Cria um arquivo de workbook de exemplo e devolve seu caminho."""
    path = tmp_path / f"{name}{suffix}"
    path.write_bytes(b"\0" * 10)
    return path


def _published_ref(
    *,
    content_type: str = "workbook",
    mode: str = "create_new",
    chunked: bool = False,
) -> PublishedRef:
    """Constrói um `PublishedRef` de exemplo para o client mock retornar."""
    return PublishedRef(
        content_id="c-1",
        name="Vendas",
        content_type=content_type,  # type: ignore[arg-type]
        project_id="p-1",
        project_name="Financeiro",
        mode=mode,  # type: ignore[arg-type]
        chunked=chunked,
        webpage_url="https://tableau.example.com/wb/c-1",
    )


# -- Caminho feliz -------------------------------------------------------------


def test_publish_workbook_arquivo_valido_chama_client_e_retorna_publishresult(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = _workbook(tmp_path)
    client.publish_workbook.return_value = _published_ref()

    result = deploy.publish_workbook(str(file_path), "Financeiro")

    assert isinstance(result, PublishResult)
    assert result.status == "success"
    assert result.content_id == "c-1"
    assert result.content_type == "workbook"
    assert result.name == "Vendas"
    assert result.project_id == "p-1"
    assert result.project_name == "Financeiro"
    assert result.mode == "create_new"
    assert result.chunked is False
    assert result.webpage_url == "https://tableau.example.com/wb/c-1"
    client.find_project_id.assert_called_once_with("Financeiro")
    client.publish_workbook.assert_called_once_with(file_path, "p-1", overwrite=False)


# -- Validação local (não chama o client) --------------------------------------


def test_publish_workbook_extensao_invalida_retorna_error_invalid_file_sem_chamar_client(  # noqa: E501
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = tmp_path / "relatorio.pdf"
    file_path.write_bytes(b"\0" * 10)

    result = deploy.publish_workbook(str(file_path), "Financeiro")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.INVALID_FILE
    session.assert_not_called()
    client.publish_workbook.assert_not_called()
    client.find_project_id.assert_not_called()


def test_publish_workbook_arquivo_inexistente_retorna_error_invalid_file(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = tmp_path / "ausente.twbx"  # não criado

    result = deploy.publish_workbook(str(file_path), "Financeiro")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.INVALID_FILE
    session.assert_not_called()
    client.publish_workbook.assert_not_called()


# -- Resolução de projeto ------------------------------------------------------


def test_publish_workbook_projeto_inexistente_retorna_error_project_not_found(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = _workbook(tmp_path)
    client.find_project_id.return_value = None

    result = deploy.publish_workbook(str(file_path), "Inexistente")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.PROJECT_NOT_FOUND
    client.publish_workbook.assert_not_called()


# -- Overwrite -----------------------------------------------------------------


def test_publish_workbook_overwrite_false_em_conteudo_existente_retorna_overwrite_not_allowed(  # noqa: E501
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = _workbook(tmp_path, name="Vendas")
    client.search_content.return_value = [
        ContentRef(id="c-1", name="Vendas", type="workbook", project="Financeiro")
    ]

    result = deploy.publish_workbook(str(file_path), "Financeiro", overwrite=False)

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.OVERWRITE_NOT_ALLOWED
    client.publish_workbook.assert_not_called()


def test_publish_workbook_overwrite_true_usa_publishmode_overwrite(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = _workbook(tmp_path, name="Vendas")
    # Mesmo com conteúdo existente, overwrite=true deve prosseguir.
    client.search_content.return_value = [
        ContentRef(id="c-1", name="Vendas", type="workbook", project="Financeiro")
    ]
    client.publish_workbook.return_value = _published_ref(mode="overwrite")

    result = deploy.publish_workbook(str(file_path), "Financeiro", overwrite=True)

    assert isinstance(result, PublishResult)
    assert result.mode == "overwrite"
    client.publish_workbook.assert_called_once_with(file_path, "p-1", overwrite=True)


def test_publish_workbook_arquivo_grande_define_chunked_true(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = _workbook(tmp_path)
    client.publish_workbook.return_value = _published_ref(chunked=True)

    result = deploy.publish_workbook(str(file_path), "Financeiro")

    assert isinstance(result, PublishResult)
    assert result.chunked is True


# -- Propagação de erro sem vazar segredo --------------------------------------


def test_publish_workbook_auth_falha_retorna_error_auth_failed_sem_vazar_token(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = _workbook(tmp_path)
    secret = "s3cr3t-value-should-never-leak"
    client.publish_workbook.side_effect = TableauClientError(
        ErrorCode.AUTH_FAILED,
        "Autenticação no Tableau falhou. Verifique o PAT configurado.",
    )

    result = deploy.publish_workbook(str(file_path), "Financeiro")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.AUTH_FAILED
    assert secret not in result.error.message


# -- Datasource ----------------------------------------------------------------


def test_publish_datasource_extensao_tdsx_aceita(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = tmp_path / "Fonte.tdsx"
    file_path.write_bytes(b"\0" * 10)
    client.publish_datasource.return_value = _published_ref(content_type="datasource")

    result = deploy.publish_datasource(str(file_path), "Financeiro")

    assert isinstance(result, PublishResult)
    assert result.content_type == "datasource"
    client.publish_datasource.assert_called_once_with(file_path, "p-1", overwrite=False)


def test_publish_datasource_extensao_invalida_rejeitada(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = tmp_path / "Fonte.twbx"  # extensão de workbook, não de datasource
    file_path.write_bytes(b"\0" * 10)

    result = deploy.publish_datasource(str(file_path), "Financeiro")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.INVALID_FILE
    session.assert_not_called()
    client.publish_datasource.assert_not_called()


# -- Publicação de extrato .hyper (RF21–RF22) ----------------------------------


def test_publish_datasource_aceita_extensao_hyper(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = tmp_path / "Extrato.hyper"
    file_path.write_bytes(b"\0" * 10)
    client.publish_datasource.return_value = _published_ref(content_type="datasource")

    result = deploy.publish_datasource(str(file_path), "Financeiro")

    assert isinstance(result, PublishResult)
    assert result.content_type == "datasource"
    client.publish_datasource.assert_called_once_with(file_path, "p-1", overwrite=False)


def test_publish_datasource_hyper_respeita_politica_de_sobrescrita(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = tmp_path / "Vendas.hyper"
    file_path.write_bytes(b"\0" * 10)
    # Já existe um datasource de mesmo nome no projeto; overwrite=false recusa.
    client.search_content.return_value = [
        ContentRef(id="c-1", name="Vendas", type="datasource", project="Financeiro")
    ]

    result = deploy.publish_datasource(str(file_path), "Financeiro", overwrite=False)

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.OVERWRITE_NOT_ALLOWED
    client.publish_datasource.assert_not_called()


def test_publish_datasource_hyper_retorna_content_id_para_encadeamento(
    tmp_path: Path, client: MagicMock, session: MagicMock
) -> None:
    file_path = tmp_path / "Vendas.hyper"
    file_path.write_bytes(b"\0" * 10)
    client.publish_datasource.return_value = _published_ref(content_type="datasource")

    result = deploy.publish_datasource(str(file_path), "Financeiro")

    assert isinstance(result, PublishResult)
    # content_id permite encadear com metadados/QA (RF22).
    assert result.content_id == "c-1"
    assert result.content_type == "datasource"

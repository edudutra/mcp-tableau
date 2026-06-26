"""Testes unitários do `TableauClient` (TSC sempre mockado, sem rede)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests.exceptions
import tableauserverclient as TSC
from tableauserverclient.server.endpoint.exceptions import (
    NotSignedInError,
    ServerResponseError,
)

from mcp_tableau.config import Settings
from mcp_tableau.models import ContentRef, ErrorCode
from mcp_tableau.tableau.client import (
    CHUNK_THRESHOLD_BYTES,
    PublishedRef,
    TableauClient,
    TableauClientError,
)


@pytest.fixture
def settings(tableau_env: dict[str, str]) -> Settings:
    """`Settings` construída a partir do ambiente de teste."""
    return Settings()  # type: ignore[call-arg]


@pytest.fixture
def server() -> MagicMock:
    """Mock do `TSC.Server` com sub-endpoints usados pelo cliente."""
    srv = MagicMock(name="Server")
    srv.PublishMode = _PUBLISH_MODE
    return srv


@pytest.fixture
def client(
    settings: Settings, server: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> TableauClient:
    """`TableauClient` cujo `TSC.Server` é substituído por um mock."""
    monkeypatch.setattr(TSC, "Server", lambda *a, **k: server)
    return TableauClient(settings)


# Referência ao enum real, capturada antes de `TSC.Server` ser monkeypatchado.
_PUBLISH_MODE = TSC.Server.PublishMode


def _server_error(http_status: int) -> ServerResponseError:
    """Constrói um `ServerResponseError` com código que embute o status HTTP."""
    return ServerResponseError(
        code=f"{http_status}003", summary="erro", detail="detalhe"
    )


# -- Sign-in / sign-out --------------------------------------------------------


def test_client_sign_in_usa_pat_da_config(
    client: TableauClient, server: MagicMock, settings: Settings
) -> None:
    client.sign_in()

    server.auth.sign_in.assert_called_once()
    (auth_req,) = server.auth.sign_in.call_args.args
    assert isinstance(auth_req, TSC.PersonalAccessTokenAuth)
    assert auth_req.token_name == settings.pat_name
    assert auth_req.personal_access_token == settings.pat_secret.get_secret_value()
    assert auth_req.site_id == settings.site


def test_client_sign_out_garantido_mesmo_em_erro(
    client: TableauClient, server: MagicMock
) -> None:
    with pytest.raises(RuntimeError, match="falha de uso"):
        with client:
            raise RuntimeError("falha de uso")

    server.auth.sign_out.assert_called_once()


def test_client_context_manager_faz_sign_in_e_sign_out(
    client: TableauClient, server: MagicMock
) -> None:
    with client:
        pass

    server.auth.sign_in.assert_called_once()
    server.auth.sign_out.assert_called_once()


def test_client_sign_out_tolera_erro_sem_propagar(
    client: TableauClient, server: MagicMock
) -> None:
    server.auth.sign_out.side_effect = NotSignedInError("sem sessão")

    client.sign_out()  # não deve levantar


# -- Re-autenticação lazy ------------------------------------------------------


def test_client_token_expirado_dispara_reauth_e_repete_uma_vez(
    client: TableauClient, server: MagicMock
) -> None:
    view = MagicMock(image=b"png-bytes")
    server.views.get_by_id.side_effect = [_server_error(401), view]

    result = client.render_view_image("v-1", {}, high_res=False)

    assert result == b"png-bytes"
    # re-auth aconteceu exatamente uma vez
    server.auth.sign_in.assert_called_once()
    # a operação (get_by_id) foi tentada duas vezes
    assert server.views.get_by_id.call_count == 2


def test_client_reauth_repete_no_maximo_uma_vez(
    client: TableauClient, server: MagicMock
) -> None:
    server.workbooks.download.side_effect = [_server_error(401), _server_error(401)]

    with pytest.raises(TableauClientError) as exc_info:
        client.download_workbook("wb-1", Path("/tmp/does-not-matter"))

    assert exc_info.value.code is ErrorCode.AUTH_FAILED
    server.auth.sign_in.assert_called_once()
    assert server.workbooks.download.call_count == 2


def test_client_notsignedin_dispara_reauth(
    client: TableauClient, server: MagicMock
) -> None:
    view = MagicMock(pdf=b"pdf-bytes")
    server.views.get_by_id.side_effect = [NotSignedInError("expirou"), view]

    result = client.render_view_pdf("v-1", "A4", {})

    assert result == b"pdf-bytes"
    server.auth.sign_in.assert_called_once()


def test_client_erro_403_nao_dispara_reauth(
    client: TableauClient, server: MagicMock
) -> None:
    server.workbooks.download.side_effect = _server_error(403)

    with pytest.raises(TableauClientError) as exc_info:
        client.download_workbook("wb-1", Path("/tmp/dest"))

    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED
    server.auth.sign_in.assert_not_called()
    server.workbooks.download.assert_called_once()


# -- Tradução de erros ---------------------------------------------------------


def test_client_traduz_serverresponseerror_404_para_not_found(
    client: TableauClient, server: MagicMock
) -> None:
    server.workbooks.download.side_effect = _server_error(404)

    with pytest.raises(TableauClientError) as exc_info:
        client.download_workbook("missing", Path("/tmp/dest"))

    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_client_traduz_403_para_permission_denied(
    client: TableauClient, server: MagicMock
) -> None:
    server.workbooks.download.side_effect = _server_error(403)

    with pytest.raises(TableauClientError) as exc_info:
        client.download_workbook("wb-1", Path("/tmp/dest"))

    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED


def test_client_traduz_401_para_auth_failed(
    client: TableauClient, server: MagicMock
) -> None:
    # 401 dispara re-auth; se persistir, o erro final é AUTH_FAILED.
    server.workbooks.download.side_effect = _server_error(401)

    with pytest.raises(TableauClientError) as exc_info:
        client.download_workbook("wb-1", Path("/tmp/dest"))

    assert exc_info.value.code is ErrorCode.AUTH_FAILED


def test_client_traduz_413_para_payload_too_large(
    client: TableauClient, server: MagicMock
) -> None:
    server.workbooks.download.side_effect = _server_error(413)

    with pytest.raises(TableauClientError) as exc_info:
        client.download_workbook("wb-1", Path("/tmp/dest"))

    assert exc_info.value.code is ErrorCode.PAYLOAD_TOO_LARGE


def test_client_traduz_5xx_para_upstream_error(
    client: TableauClient, server: MagicMock
) -> None:
    server.workbooks.download.side_effect = _server_error(500)

    with pytest.raises(TableauClientError) as exc_info:
        client.download_workbook("wb-1", Path("/tmp/dest"))

    assert exc_info.value.code is ErrorCode.UPSTREAM_ERROR


def test_client_nunca_inclui_pat_em_mensagem_de_erro(
    client: TableauClient, server: MagicMock, settings: Settings
) -> None:
    secret = settings.pat_secret.get_secret_value()
    pat_name = settings.pat_name
    for status in (401, 403, 404, 413, 500):
        server.workbooks.download.side_effect = _server_error(status)
        with pytest.raises(TableauClientError) as exc_info:
            client.download_workbook("wb-1", Path("/tmp/dest"))
        message = exc_info.value.message
        assert secret not in message
        assert pat_name not in message


def test_client_sign_in_falho_nao_vaza_segredo(
    client: TableauClient, server: MagicMock, settings: Settings
) -> None:
    secret = settings.pat_secret.get_secret_value()
    server.auth.sign_in.side_effect = _server_error(401)

    with pytest.raises(TableauClientError) as exc_info:
        client.sign_in()

    assert exc_info.value.code is ErrorCode.AUTH_FAILED
    assert secret not in exc_info.value.message


# -- TLS / CA bundle (regressão BUG-02) ----------------------------------------


def test_client_traduz_sslerror_para_upstream_com_mensagem_acionavel(
    client: TableauClient, server: MagicMock
) -> None:
    # Regressão BUG-02: erro de TLS (CA corporativa não confiável) não é um
    # ServerResponseError; sem tratamento explícito caía no fallback genérico
    # "Falha inesperada", sem orientar a causa real.
    server.auth.sign_in.side_effect = requests.exceptions.SSLError(
        "self-signed certificate in certificate chain"
    )

    with pytest.raises(TableauClientError) as exc_info:
        client.sign_in()

    assert exc_info.value.code is ErrorCode.UPSTREAM_ERROR
    mensagem = exc_info.value.message
    assert "TLS" in mensagem
    assert "TABLEAU_CA_BUNDLE" in mensagem
    assert "inesperada" not in mensagem


def test_client_traduz_connectionerror_para_upstream_com_mensagem_acionavel(
    client: TableauClient, server: MagicMock
) -> None:
    server.auth.sign_in.side_effect = requests.exceptions.ConnectionError(
        "Connection refused"
    )

    with pytest.raises(TableauClientError) as exc_info:
        client.sign_in()

    assert exc_info.value.code is ErrorCode.UPSTREAM_ERROR
    assert "conexão" in exc_info.value.message.lower()


def test_client_ca_bundle_configura_verify_no_tsc(
    server: MagicMock, tableau_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regressão BUG-02: a aplicação precisa expor configuração de CA bundle.
    monkeypatch.setenv("TABLEAU_CA_BUNDLE", "/etc/ssl/certs/ca-certificates.crt")
    monkeypatch.setattr(TSC, "Server", lambda *a, **k: server)

    TableauClient(Settings())  # type: ignore[call-arg]

    enviados = [chamada.args[0] for chamada in server.add_http_options.call_args_list]
    assert any(
        opt.get("verify") == "/etc/ssl/certs/ca-certificates.crt" for opt in enviados
    )


def test_client_sem_ca_bundle_nao_define_verify(
    client: TableauClient, server: MagicMock
) -> None:
    # `client` usa Settings sem TABLEAU_CA_BUNDLE: o `verify` padrão do certifi é
    # mantido (nenhum override é enviado ao TSC).
    enviados = [chamada.args[0] for chamada in server.add_http_options.call_args_list]
    assert enviados  # add_http_options foi chamado (timeout)
    assert all("verify" not in opt for opt in enviados)


# -- Publicação ----------------------------------------------------------------


def _twbx(tmp_path: Path, size: int) -> Path:
    path = tmp_path / "wb.twbx"
    path.write_bytes(b"\0" * size)
    return path


def test_client_publish_workbook_create_new_retorna_ref(
    client: TableauClient, server: MagicMock, tmp_path: Path
) -> None:
    file_path = _twbx(tmp_path, 10)
    published = MagicMock(
        id="wb-id", name="Vendas", project_id="p-1", webpage_url="http://x"
    )
    server.workbooks.publish.return_value = published
    server.projects.get_by_id.return_value = MagicMock(name="Financeiro")
    server.projects.get_by_id.return_value.name = "Financeiro"

    ref = client.publish_workbook(file_path, "p-1", overwrite=False)

    assert isinstance(ref, PublishedRef)
    assert ref.content_id == "wb-id"
    assert ref.content_type == "workbook"
    assert ref.mode == "create_new"
    assert ref.chunked is False
    assert ref.project_name == "Financeiro"
    _, _, mode = server.workbooks.publish.call_args.args
    assert mode == _PUBLISH_MODE.CreateNew


def test_client_publish_workbook_overwrite_usa_publishmode_overwrite(
    client: TableauClient, server: MagicMock, tmp_path: Path
) -> None:
    file_path = _twbx(tmp_path, 10)
    server.workbooks.publish.return_value = MagicMock(id="wb", name="W", project_id="p")
    server.projects.get_by_id.return_value.name = "Proj"

    ref = client.publish_workbook(file_path, "p", overwrite=True)

    assert ref.mode == "overwrite"
    _, _, mode = server.workbooks.publish.call_args.args
    assert mode == _PUBLISH_MODE.Overwrite


def test_client_publish_arquivo_grande_marca_chunked(
    client: TableauClient, server: MagicMock, tmp_path: Path
) -> None:
    file_path = _twbx(tmp_path, CHUNK_THRESHOLD_BYTES + 1)
    server.workbooks.publish.return_value = MagicMock(id="wb", name="W", project_id="p")
    server.projects.get_by_id.return_value.name = "Proj"

    ref = client.publish_workbook(file_path, "p", overwrite=False)

    assert ref.chunked is True


def test_client_publish_arquivo_pequeno_nao_marca_chunked(
    client: TableauClient, server: MagicMock, tmp_path: Path
) -> None:
    file_path = _twbx(tmp_path, 1024)
    server.workbooks.publish.return_value = MagicMock(id="wb", name="W", project_id="p")
    server.projects.get_by_id.return_value.name = "Proj"

    ref = client.publish_workbook(file_path, "p", overwrite=False)

    assert ref.chunked is False


def test_client_publish_datasource_delega_para_datasources(
    client: TableauClient, server: MagicMock, tmp_path: Path
) -> None:
    file_path = tmp_path / "ds.tdsx"
    file_path.write_bytes(b"\0" * 10)
    server.datasources.publish.return_value = MagicMock(
        id="ds", name="DS", project_id="p"
    )
    server.projects.get_by_id.return_value.name = "Proj"

    ref = client.publish_datasource(file_path, "p", overwrite=False)

    assert ref.content_type == "datasource"
    server.datasources.publish.assert_called_once()


# -- Download ------------------------------------------------------------------


def test_client_download_workbook_cria_dir_e_retorna_path(
    client: TableauClient, server: MagicMock, tmp_path: Path
) -> None:
    dest = tmp_path / "out"
    server.workbooks.download.return_value = str(dest / "wb.twbx")

    result = client.download_workbook("wb-1", dest)

    assert result == dest / "wb.twbx"
    assert dest.is_dir()
    server.workbooks.download.assert_called_once()


# -- Renderização --------------------------------------------------------------


def test_client_render_view_image_aplica_filtros_e_alta_resolucao(
    client: TableauClient, server: MagicMock
) -> None:
    view = MagicMock(image=b"png")
    server.views.get_by_id.return_value = view

    result = client.render_view_image(
        "v-1", {"Region": "West", "Year": "2026"}, high_res=True
    )

    assert result == b"png"
    options = server.views.populate_image.call_args.args[1]
    assert options.image_resolution == TSC.ImageRequestOptions.Resolution.High
    params = options.get_query_params()
    assert params["vf_Region"] == "West"
    assert params["vf_Year"] == "2026"


def test_client_render_view_image_sem_alta_resolucao(
    client: TableauClient, server: MagicMock
) -> None:
    view = MagicMock(image=b"png")
    server.views.get_by_id.return_value = view

    client.render_view_image("v-1", {}, high_res=False)

    options = server.views.populate_image.call_args.args[1]
    assert options.image_resolution is None


def test_client_render_view_pdf_define_page_type_e_filtros(
    client: TableauClient, server: MagicMock
) -> None:
    view = MagicMock(pdf=b"pdf")
    server.views.get_by_id.return_value = view

    result = client.render_view_pdf("v-1", "A4", {"Region": "West"})

    assert result == b"pdf"
    options = server.views.populate_pdf.call_args.args[1]
    assert options.page_type == TSC.PDFRequestOptions.PageType.A4
    assert options.get_query_params()["vf_Region"] == "West"


def test_client_render_view_pdf_page_type_invalido_vira_unspecified(
    client: TableauClient, server: MagicMock
) -> None:
    server.views.get_by_id.return_value = MagicMock(pdf=b"pdf")

    client.render_view_pdf("v-1", "Inexistente", {})

    options = server.views.populate_pdf.call_args.args[1]
    assert options.page_type == TSC.PDFRequestOptions.PageType.Unspecified


# -- Resolução de projeto e busca ---------------------------------------------


def test_client_find_project_id_retorna_luid_do_nome(
    client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    p1 = MagicMock(id="p-1")
    p1.name = "Financeiro"
    p2 = MagicMock(id="p-2")
    p2.name = "Marketing"
    monkeypatch.setattr(TSC, "Pager", lambda endpoint, *a, **k: iter([p1, p2]))

    assert client.find_project_id("Marketing") == "p-2"


def test_client_find_project_id_nao_encontrado_retorna_none(
    client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TSC, "Pager", lambda endpoint, *a, **k: iter([]))

    assert client.find_project_id("Inexistente") is None


def test_client_paginacao_lista_todo_o_conteudo(
    client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbooks = []
    for i in range(150):
        wb = MagicMock(id=f"wb-{i}", project_name="Proj")
        wb.name = f"Relatório Vendas {i}"
        workbooks.append(wb)
    datasources = []
    for i in range(120):
        ds = MagicMock(id=f"ds-{i}", project_name="Proj")
        ds.name = f"Fonte Vendas {i}"
        datasources.append(ds)

    def fake_pager(endpoint, *a, **k):  # type: ignore[no-untyped-def]
        if endpoint is server.workbooks:
            return iter(workbooks)
        if endpoint is server.datasources:
            return iter(datasources)
        return iter([])

    monkeypatch.setattr(TSC, "Pager", fake_pager)

    results = client.search_content("vendas")

    assert len(results) == 270
    assert all(isinstance(r, ContentRef) for r in results)
    assert sum(1 for r in results if r.type == "workbook") == 150
    assert sum(1 for r in results if r.type == "datasource") == 120


def test_client_search_content_filtra_por_termo(
    client: TableauClient, server: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    wb_match = MagicMock(id="wb-1", project_name="P")
    wb_match.name = "Painel de Vendas"
    wb_miss = MagicMock(id="wb-2", project_name="P")
    wb_miss.name = "Estoque"

    def fake_pager(endpoint, *a, **k):  # type: ignore[no-untyped-def]
        if endpoint is server.workbooks:
            return iter([wb_match, wb_miss])
        return iter([])

    monkeypatch.setattr(TSC, "Pager", fake_pager)

    results = client.search_content("vendas")

    assert [r.id for r in results] == ["wb-1"]

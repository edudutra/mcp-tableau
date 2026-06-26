"""Cliente REST do Tableau (`TableauClient`).

Único componente que fala REST com o Tableau via `tableauserverclient` (TSC).
Centraliza:

- autenticação PAT com sign-in/sign-out garantido (context manager);
- re-autenticação *lazy*: token expirado/401 dispara re-auth e repete a operação
  exatamente **uma** vez;
- publicação de workbook/datasource com ``PublishMode`` e chunking automático
  acima de 64 MB (flag ``chunked`` no resultado);
- download de artefato e renderização de imagem/PDF (``populate_image`` /
  ``populate_pdf`` com filtros ``vf_`` e ``resolution=high``);
- resolução de projeto por nome e listagem/paginação completa de conteúdo;
- tradução de exceções do TSC para códigos do envelope `ToolError`.

Nenhuma credencial (PAT name/secret, token de sessão) aparece em mensagens de
erro ou logs: as mensagens são construídas manualmente a partir de dados não
sensíveis (código/summary da API).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import tableauserverclient as TSC
from tableauserverclient.server.endpoint.exceptions import (
    InternalServerError,
    NotSignedInError,
    ServerResponseError,
)

from mcp_tableau.models import ContentRef, ErrorCode

if TYPE_CHECKING:
    from mcp_tableau.config import Settings

# Limite de upload único do Tableau; acima disso o TSC particiona em chunks.
CHUNK_THRESHOLD_BYTES = 64 * 1024 * 1024

# Tipos de página aceitos pela Query View PDF (espelha PDFRequestOptions.PageType).
PageType = Literal[
    "A3",
    "A4",
    "A5",
    "B4",
    "B5",
    "Executive",
    "Folio",
    "Ledger",
    "Legal",
    "Letter",
    "Note",
    "Quarto",
    "Tabloid",
    "Unspecified",
]


class TableauClientError(Exception):
    """Erro da camada de integração, já traduzido para um `ErrorCode`.

    Carrega o código acionável que as tools (tarefas futuras) usam para montar o
    envelope `ToolError`. A mensagem é sempre livre de credenciais.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class PublishedRef:
    """Resultado interno de uma publicação, consumido pelas tools de deploy.

    As tools montam o `PublishResult` final (Pydantic) a partir deste objeto.
    """

    content_id: str
    name: str
    content_type: Literal["workbook", "datasource"]
    project_id: str
    project_name: str
    mode: Literal["create_new", "overwrite"]
    chunked: bool
    webpage_url: str | None = None


def _http_status_from_code(code: str) -> int | None:
    """Extrai o status HTTP do código do TSC (ex.: ``"404003"`` -> ``404``).

    O `tableauserverclient` codifica o erro como ``<http><subcode>``; os três
    primeiros dígitos são o status HTTP.
    """
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) >= 3:
        with contextlib.suppress(ValueError):
            return int(digits[:3])
    return None


def _is_auth_error(exc: ServerResponseError) -> bool:
    """Indica se o erro REST representa sessão expirada/não autenticada (401)."""
    return _http_status_from_code(exc.code) == 401


def _translate(exc: Exception) -> TableauClientError:
    """Traduz uma exceção do TSC para `TableauClientError` (código + mensagem).

    Garante que nenhuma credencial vaze: a mensagem usa apenas o status/summary
    da API, nunca o PAT ou o token de sessão.
    """
    if isinstance(exc, NotSignedInError):
        return TableauClientError(
            ErrorCode.AUTH_FAILED,
            "Sessão do Tableau inválida ou expirada. Verifique o PAT configurado.",
        )
    if isinstance(exc, InternalServerError):
        return TableauClientError(
            ErrorCode.UPSTREAM_ERROR,
            "Falha interna do Tableau ao processar a requisição. Tente novamente.",
        )
    if isinstance(exc, ServerResponseError):
        status = _http_status_from_code(exc.code)
        if status == 401:
            return TableauClientError(
                ErrorCode.AUTH_FAILED,
                "Autenticação no Tableau falhou. Verifique o PAT configurado.",
            )
        if status == 403:
            return TableauClientError(
                ErrorCode.PERMISSION_DENIED,
                "Permissão negada pelo Tableau para esta operação.",
            )
        if status == 404:
            return TableauClientError(
                ErrorCode.NOT_FOUND,
                "Recurso não encontrado no Tableau.",
            )
        if status == 413:
            return TableauClientError(
                ErrorCode.PAYLOAD_TOO_LARGE,
                "Arquivo excede o limite do servidor Tableau, mesmo com chunking.",
            )
        return TableauClientError(
            ErrorCode.UPSTREAM_ERROR,
            "Falha ao comunicar com o Tableau. Tente novamente.",
        )
    return TableauClientError(
        ErrorCode.UPSTREAM_ERROR,
        "Falha inesperada ao comunicar com o Tableau.",
    )


class TableauClient:
    """Sessão TSC gerenciada (PAT), com re-autenticação *lazy* em expiração/401.

    Uso recomendado como context manager::

        with TableauClient(settings) as client:
            ref = client.publish_workbook(path, project_id, overwrite=True)

    O sign-out é garantido na saída do bloco, inclusive em caso de exceção.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._server = TSC.Server(settings.server_url, use_server_version=True)
        self._server.add_http_options({"timeout": settings.request_timeout})

    # -- Ciclo de vida da sessão ------------------------------------------------

    def _auth(self) -> TSC.PersonalAccessTokenAuth:
        """Constrói as credenciais PAT a partir da `Settings` (segredo lido aqui)."""
        return TSC.PersonalAccessTokenAuth(
            token_name=self._settings.pat_name,
            personal_access_token=self._settings.pat_secret.get_secret_value(),
            site_id=self._settings.site,
        )

    def sign_in(self) -> None:
        """Autentica no Tableau com o PAT da configuração."""
        try:
            self._server.auth.sign_in(self._auth())
        except Exception as exc:  # noqa: BLE001 - traduzido p/ erro acionável
            raise _translate(exc) from exc

    def sign_out(self) -> None:
        """Encerra a sessão; tolera ausência de sessão sem propagar erro."""
        with contextlib.suppress(Exception):
            self._server.auth.sign_out()

    def __enter__(self) -> TableauClient:
        self.sign_in()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.sign_out()

    @property
    def server(self) -> TSC.Server:
        """Sessão TSC autenticada, reaproveitada pelo `MetadataClient`.

        O `MetadataClient` deve usar este `Server` (mesma sessão/token) em vez de
        abrir uma autenticação própria.
        """
        return self._server

    # -- Re-autenticação lazy ---------------------------------------------------

    def _with_reauth(self, operation):  # type: ignore[no-untyped-def]
        """Executa ``operation()`` e, em 401/sessão expirada, re-autentica e repete.

        A operação é repetida no máximo **uma** vez. Outros erros do TSC são
        traduzidos para `TableauClientError`.
        """
        try:
            return operation()
        except (ServerResponseError, NotSignedInError) as exc:
            if isinstance(exc, NotSignedInError) or _is_auth_error(exc):
                self.sign_in()
                try:
                    return operation()
                except Exception as retry_exc:  # noqa: BLE001
                    raise _translate(retry_exc) from retry_exc
            raise _translate(exc) from exc
        except Exception as exc:  # noqa: BLE001 - demais erros TSC traduzidos
            raise _translate(exc) from exc

    # -- Publicação -------------------------------------------------------------

    def publish_workbook(
        self, file_path: Path, project_id: str, overwrite: bool
    ) -> PublishedRef:
        """Publica/sobrescreve um workbook em um projeto.

        Chunking é automático para arquivos acima de 64 MB; a flag ``chunked``
        do resultado reflete esse caminho.
        """
        return self._publish("workbook", file_path, project_id, overwrite)

    def publish_datasource(
        self, file_path: Path, project_id: str, overwrite: bool
    ) -> PublishedRef:
        """Publica/sobrescreve uma fonte de dados em um projeto."""
        return self._publish("datasource", file_path, project_id, overwrite)

    def _publish(
        self,
        content_type: Literal["workbook", "datasource"],
        file_path: Path,
        project_id: str,
        overwrite: bool,
    ) -> PublishedRef:
        mode = (
            self._server.PublishMode.Overwrite
            if overwrite
            else self._server.PublishMode.CreateNew
        )
        mode_label: Literal["create_new", "overwrite"] = (
            "overwrite" if overwrite else "create_new"
        )
        chunked = file_path.stat().st_size > CHUNK_THRESHOLD_BYTES
        file_arg = str(file_path)

        if content_type == "workbook":
            item = TSC.WorkbookItem(project_id=project_id)

            def op() -> TSC.WorkbookItem:
                return self._server.workbooks.publish(item, file_arg, mode)
        else:
            item = TSC.DatasourceItem(project_id=project_id)

            def op() -> TSC.DatasourceItem:
                return self._server.datasources.publish(item, file_arg, mode)

        published = self._with_reauth(op)
        project_name = self._resolve_project_name(published.project_id)
        return PublishedRef(
            content_id=published.id,
            name=published.name,
            content_type=content_type,
            project_id=published.project_id,
            project_name=project_name,
            mode=mode_label,
            chunked=chunked,
            webpage_url=getattr(published, "webpage_url", None),
        )

    def _resolve_project_name(self, project_id: str | None) -> str:
        """Resolve o nome do projeto pelo id; vazio se indisponível."""
        if not project_id:
            return ""
        with contextlib.suppress(Exception):
            project = self._with_reauth(
                lambda: self._server.projects.get_by_id(project_id)
            )
            if project is not None and project.name:
                return project.name
        return ""

    # -- Download ---------------------------------------------------------------

    def download_workbook(self, workbook_id: str, dest_dir: Path) -> Path:
        """Baixa o artefato do workbook para ``dest_dir`` e retorna o caminho."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = self._with_reauth(
            lambda: self._server.workbooks.download(
                workbook_id, filepath=str(dest_dir), include_extract=True
            )
        )
        return Path(path)

    # -- Renderização -----------------------------------------------------------

    def render_view_image(
        self, view_id: str, filters: dict[str, str], high_res: bool
    ) -> bytes:
        """Renderiza a view como PNG, aplicando filtros ``vf_`` e alta resolução."""
        options = TSC.ImageRequestOptions(maxage=1)
        if high_res:
            options.image_resolution = TSC.ImageRequestOptions.Resolution.High
        for name, value in filters.items():
            options.vf(name, value)

        def op() -> bytes:
            view = self._server.views.get_by_id(view_id)
            self._server.views.populate_image(view, options)
            return view.image

        return self._with_reauth(op)

    def render_view_pdf(
        self, view_id: str, page_type: str, filters: dict[str, str]
    ) -> bytes:
        """Renderiza a view como PDF com ``page_type`` e filtros ``vf_``."""
        options = TSC.PDFRequestOptions(page_type=self._page_type(page_type), maxage=1)
        for name, value in filters.items():
            options.vf(name, value)

        def op() -> bytes:
            view = self._server.views.get_by_id(view_id)
            self._server.views.populate_pdf(view, options)
            return view.pdf

        return self._with_reauth(op)

    @staticmethod
    def _page_type(page_type: str) -> str:
        """Mapeia o nome do tipo de página para o enum de `PDFRequestOptions`."""
        return getattr(
            TSC.PDFRequestOptions.PageType,
            page_type,
            TSC.PDFRequestOptions.PageType.Unspecified,
        )

    # -- Resolução de projeto e busca ------------------------------------------

    def find_project_id(self, project_name: str) -> str | None:
        """Resolve o LUID de um projeto pelo nome exato; ``None`` se ausente."""

        def op() -> str | None:
            for project in TSC.Pager(self._server.projects):
                if project.name == project_name:
                    return project.id
            return None

        return self._with_reauth(op)

    def search_content(self, term: str) -> list[ContentRef]:
        """Lista workbooks e datasources cujo nome contém ``term`` (case-insensitive).

        Pagina todo o conteúdo (via `Pager`), sem truncar resultados.
        """
        needle = term.casefold()

        def op() -> list[ContentRef]:
            results: list[ContentRef] = []
            for workbook in TSC.Pager(self._server.workbooks):
                if needle in (workbook.name or "").casefold():
                    results.append(
                        ContentRef(
                            id=workbook.id,
                            name=workbook.name,
                            type="workbook",
                            project=workbook.project_name,
                        )
                    )
            for datasource in TSC.Pager(self._server.datasources):
                if needle in (datasource.name or "").casefold():
                    results.append(
                        ContentRef(
                            id=datasource.id,
                            name=datasource.name,
                            type="datasource",
                            project=datasource.project_name,
                        )
                    )
            return results

        return self._with_reauth(op)


@contextlib.contextmanager
def tableau_session(settings: Settings) -> Iterator[TableauClient]:
    """Context manager utilitário: abre e garante o sign-out da sessão."""
    client = TableauClient(settings)
    client.sign_in()
    try:
        yield client
    finally:
        client.sign_out()

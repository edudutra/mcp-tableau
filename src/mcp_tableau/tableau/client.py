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
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

import requests.exceptions
import tableauserverclient as TSC
from tableauserverclient.server.endpoint.exceptions import (
    InternalServerError,
    NotSignedInError,
    ServerResponseError,
)

from mcp_tableau.models import ContentRef, ErrorCode, PermContentType

if TYPE_CHECKING:
    from mcp_tableau.config import Settings

# Limite de upload único do Tableau; acima disso o TSC particiona em chunks.
CHUNK_THRESHOLD_BYTES = 64 * 1024 * 1024

# Tipo de retorno genérico das operações encapsuladas por `_with_reauth`.
T = TypeVar("T")

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
    # Erros de transporte do `requests` (TLS/conexão) não são `ServerResponseError`;
    # sem este tratamento cairiam no fallback genérico e mascarariam a causa real
    # (ex.: CA corporativa não confiável em rede com interceptação TLS).
    if isinstance(exc, requests.exceptions.SSLError):
        return TableauClientError(
            ErrorCode.UPSTREAM_ERROR,
            "Falha de TLS ao conectar ao Tableau (certificado não confiável). "
            "Verifique o CA bundle da rede (TABLEAU_CA_BUNDLE) ou o proxy corporativo.",
        )
    if isinstance(exc, requests.exceptions.ConnectionError):
        return TableauClientError(
            ErrorCode.UPSTREAM_ERROR,
            "Falha de conexão de rede com o Tableau. Verifique a URL do servidor, "
            "a conectividade e o proxy/CA bundle (TABLEAU_CA_BUNDLE).",
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
        http_options: dict[str, object] = {"timeout": settings.request_timeout}
        # CA bundle corporativo opcional: aponta a verificação TLS do `requests`
        # para o PEM configurado em vez do store padrão do `certifi`.
        if settings.ca_bundle:
            http_options["verify"] = settings.ca_bundle
        self._server.add_http_options(http_options)

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

    def _with_reauth(self, operation: Callable[[], T]) -> T:
        """Executa ``operation()`` e, em 401/sessão expirada, re-autentica e repete.

        A operação é repetida no máximo **uma** vez. Outros erros do TSC são
        traduzidos para `TableauClientError`. Se a operação já levantou um
        ``TableauClientError`` (tradução feita internamente), ele é propagado
        sem re-tradução.
        """
        try:
            return operation()
        except TableauClientError:
            raise
        except (ServerResponseError, NotSignedInError) as exc:
            if isinstance(exc, NotSignedInError) or _is_auth_error(exc):
                self.sign_in()
                try:
                    return operation()
                except TableauClientError:
                    raise
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

    # -- Views ------------------------------------------------------------------

    def list_workbook_view_luids(self, workbook_id: str) -> dict[str, str]:
        """Mapa nome_da_view -> LUID das views publicadas do workbook.

        Executa uma única chamada ``workbooks.populate_views`` (``usage=False``,
        sem estatísticas de uso) e monta o dicionário ``{view.name: view.id}``.
        Views sem LUID (ex.: sheets ocultas/não publicadas) são **omitidas** do
        mapa. Em caso de nomes duplicados, a última ocorrência prevalece (ordem
        natural de iteração de ``workbook_item.views``).

        A operação é envolvida em :meth:`_with_reauth`: 401/sessão expirada
        dispara re-autenticação e repete exatamente uma vez; demais erros do TSC
        são traduzidos para `TableauClientError` com o `ErrorCode` adequado, sem
        vazar credenciais.
        """

        def op() -> dict[str, str]:
            workbook_item = self._server.workbooks.get_by_id(workbook_id)
            self._server.workbooks.populate_views(workbook_item, usage=False)
            return {view.name: view.id for view in workbook_item.views if view.id}

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

    # -- Resolução de usuários e grupos (Capacidade 6) -------------------------

    def resolve_user(self, name: str) -> tuple[str, str]:
        """Resolve um nome de usuário (site username) para ``(LUID, site_role)``.

        Usa filtro server-side (``server.users.filter(name=...)``), conforme
        ADR-004. Levanta ``TableauClientError(NOT_FOUND)`` se o usuário não
        existir no site.
        """

        def op() -> tuple[str, str]:
            req_options = TSC.RequestOptions()
            req_options.filter.add(
                TSC.Filter(
                    TSC.RequestOptions.Field.Name,
                    TSC.RequestOptions.Operator.Equals,
                    name,
                )
            )
            users, _ = self._server.users.get(req_options)
            if not users:
                raise TableauClientError(
                    ErrorCode.NOT_FOUND,
                    f"Usuário '{name}' não encontrado no site.",
                )
            user = users[0]
            return (user.id, user.site_role or "")

        return self._with_reauth(op)

    def list_users(self, name_filter: str | None = None) -> list[tuple[str, str, str]]:
        """Lista usuários do site; retorna lista de ``(id, name, site_role)``.

        Se ``name_filter`` for fornecido, aplica filtro server-side por nome
        (contains). Paginação completa via ``TSC.Pager``.
        """

        def op() -> list[tuple[str, str, str]]:
            req_options = TSC.RequestOptions()
            if name_filter:
                req_options.filter.add(
                    TSC.Filter(
                        TSC.RequestOptions.Field.Name,
                        TSC.RequestOptions.Operator.Equals,
                        name_filter,
                    )
                )
            results: list[tuple[str, str, str]] = []
            for user in TSC.Pager(self._server.users, req_options):
                results.append((user.id, user.name or "", user.site_role or ""))
            return results

        return self._with_reauth(op)

    def resolve_group(self, name: str) -> tuple[str, int | None]:
        """Resolve um nome de grupo para ``(LUID, user_count)``.

        Usa filtro server-side (``server.groups.filter(name=...)``), conforme
        ADR-004. Levanta ``TableauClientError(NOT_FOUND)`` se o grupo não existir.
        """

        def op() -> tuple[str, int | None]:
            req_options = TSC.RequestOptions()
            req_options.filter.add(
                TSC.Filter(
                    TSC.RequestOptions.Field.Name,
                    TSC.RequestOptions.Operator.Equals,
                    name,
                )
            )
            groups, _ = self._server.groups.get(req_options)
            if not groups:
                raise TableauClientError(
                    ErrorCode.NOT_FOUND,
                    f"Grupo '{name}' não encontrado no site.",
                )
            group = groups[0]
            user_count = getattr(group, "user_count", None)
            return (group.id, user_count)

        return self._with_reauth(op)

    def list_groups(
        self, name_filter: str | None = None
    ) -> list[tuple[str, str, int | None]]:
        """Lista grupos do site; retorna lista de ``(id, name, user_count)``.

        Se ``name_filter`` for fornecido, aplica filtro server-side por nome.
        Paginação completa via ``TSC.Pager``.
        """

        def op() -> list[tuple[str, str, int | None]]:
            req_options = TSC.RequestOptions()
            if name_filter:
                req_options.filter.add(
                    TSC.Filter(
                        TSC.RequestOptions.Field.Name,
                        TSC.RequestOptions.Operator.Equals,
                        name_filter,
                    )
                )
            results: list[tuple[str, str, int | None]] = []
            for group in TSC.Pager(self._server.groups, req_options):
                user_count = getattr(group, "user_count", None)
                results.append((group.id, group.name or "", user_count))
            return results

        return self._with_reauth(op)

    def list_group_members(self, group_id: str) -> list[tuple[str, str, str]]:
        """Lista membros de um grupo; retorna lista de ``(id, name, site_role)``.

        Usa ``populate_users`` para carregar os membros e pagina via ``TSC.Pager``.
        """

        def op() -> list[tuple[str, str, str]]:
            req_options = TSC.RequestOptions()
            results: list[tuple[str, str, str]] = []
            for user in TSC.Pager(
                lambda opts: self._server.groups.populate_users(
                    self._server.groups.get_by_id(group_id), opts
                ),
                req_options,
            ):
                results.append((user.id, user.name or "", user.site_role or ""))
            return results

        return self._with_reauth(op)

    # -- Lock state e resolução de projeto pai ---------------------------------

    def get_project_lock_state(self, project_id: str) -> str:
        """Retorna o valor de ``content_permissions`` do projeto.

        Valores possíveis: ``"ManagedByOwner"``, ``"LockedToProject"``,
        ``"LockedToProjectWithoutNested"``.
        """

        def op() -> str:
            project = self._server.projects.get_by_id(project_id)
            return project.content_permissions or "ManagedByOwner"

        return self._with_reauth(op)

    def get_content_project_id(
        self, content_type: PermContentType, content_id: str
    ) -> str:
        """Retorna o ``project_id`` do item de conteúdo informado.

        Para ``PermContentType.project``, retorna o próprio ``content_id`` (um
        projeto é seu próprio container). Para os demais tipos, busca o item via
        ``get_by_id`` e retorna ``project_id``.
        """
        if content_type == PermContentType.project:
            return content_id

        # Dispatch para o endpoint correto por tipo de conteúdo.
        _endpoint_map: dict[PermContentType, object] = {
            PermContentType.workbook: self._server.workbooks,
            PermContentType.datasource: self._server.datasources,
            PermContentType.view: self._server.views,
            PermContentType.flow: self._server.flows,
            PermContentType.virtual_connection: self._server.virtual_connections,
        }
        endpoint = _endpoint_map.get(content_type)
        if endpoint is None:
            raise TableauClientError(
                ErrorCode.NOT_FOUND,
                f"Tipo de conteúdo '{content_type}' não suportado.",
            )

        def op() -> str:
            item = endpoint.get_by_id(content_id)  # type: ignore[union-attr]
            project_id = getattr(item, "project_id", None)
            if not project_id:
                raise TableauClientError(
                    ErrorCode.NOT_FOUND,
                    f"Não foi possível determinar o projeto do "
                    f"{content_type} '{content_id}'.",
                )
            return project_id

        return self._with_reauth(op)

    # -- Dispatch de permissões (Capacidade 6, ADR-003) --------------------------

    # Tipo interno do dispatch: tupla (endpoint TSC, função de fetch do item por ID).
    # O endpoint expõe `populate_permissions`, `update_permissions` (ou
    # `add_permissions` para virtual_connection), e `delete_permission`.
    # A função de fetch retorna o item TSC necessário para as chamadas de
    # permissão.

    @property
    def _perm_dispatch(
        self,
    ) -> dict[PermContentType, tuple[object, Callable[[str], object]]]:
        """Mapeamento de ``PermContentType`` → (endpoint, fetch_item_by_id).

        Construído como property para acessar ``self._server`` (disponível
        apenas após ``__init__``). A indireção é mínima — um dict lookup por
        chamada.
        """
        return {
            PermContentType.project: (
                self._server.projects,
                self._server.projects.get_by_id,
            ),
            PermContentType.workbook: (
                self._server.workbooks,
                self._server.workbooks.get_by_id,
            ),
            PermContentType.datasource: (
                self._server.datasources,
                self._server.datasources.get_by_id,
            ),
            PermContentType.view: (
                self._server.views,
                self._server.views.get_by_id,
            ),
            PermContentType.flow: (
                self._server.flows,
                self._server.flows.get_by_id,
            ),
            PermContentType.virtual_connection: (
                self._server.virtual_connections,
                self._server.virtual_connections.get_by_id,
            ),
        }

    def _validate_content_type(self, content_type: PermContentType) -> None:
        """Valida que o ``content_type`` é suportado pelo dispatch."""
        if content_type not in self._perm_dispatch:
            raise TableauClientError(
                ErrorCode.VALIDATION_ERROR,
                f"Tipo de conteúdo '{content_type}' não suportado para permissões.",
            )

    def _check_view_show_tabs(
        self, content_type: PermContentType, item: object
    ) -> None:
        """Para views, verifica se ``showTabs`` está habilitado no workbook pai.

        Quando ``showTabs=True``, o Tableau ignora permissões em nível de view
        (usa as do workbook). O método levanta ``TableauClientError(SHOW_TABS_ENABLED)``
        para que as tools possam fornecer orientação clara ao agente.
        """
        if content_type != PermContentType.view:
            return
        workbook_id = getattr(item, "workbook_id", None)
        if not workbook_id:
            return

        def fetch_wb() -> object:
            return self._server.workbooks.get_by_id(workbook_id)

        workbook = self._with_reauth(fetch_wb)
        if getattr(workbook, "show_tabs", False):
            raise TableauClientError(
                ErrorCode.SHOW_TABS_ENABLED,
                "O workbook pai tem 'showTabs' habilitado. "
                "Permissões em nível de view são ignoradas pelo Tableau nesse modo. "
                "Altere as permissões no workbook ou desabilite showTabs.",
            )

    def get_permissions(
        self, content_type: PermContentType, content_id: str
    ) -> list[object]:
        """Obtém as regras de permissão de qualquer tipo de conteúdo.

        Retorna ``list[TSC.PermissionsRule]``. O dispatch é feito via
        ``_perm_dispatch`` (ADR-003).
        """
        self._validate_content_type(content_type)
        endpoint, fetch_item = self._perm_dispatch[content_type]

        def op() -> list[object]:
            item = fetch_item(content_id)
            endpoint.populate_permissions(item)
            return item.permissions

        return self._with_reauth(op)

    def update_permissions(
        self,
        content_type: PermContentType,
        content_id: str,
        rules: list[object],
    ) -> list[object]:
        """Aplica (adiciona/atualiza) regras de permissão em um conteúdo.

        Retorna a lista atualizada de ``TSC.PermissionsRule`` conforme retornada
        pelo servidor. Para ``virtual_connection`` usa ``add_permissions``
        (nome diferente na TSC).
        """
        self._validate_content_type(content_type)
        endpoint, fetch_item = self._perm_dispatch[content_type]

        def op() -> list[object]:
            item = fetch_item(content_id)
            self._check_view_show_tabs(content_type, item)
            # virtual_connections usa `add_permissions` em vez de `update_permissions`
            if content_type == PermContentType.virtual_connection:
                return endpoint.add_permissions(item, rules)
            return endpoint.update_permissions(item, rules)

        return self._with_reauth(op)

    def delete_permission(
        self,
        content_type: PermContentType,
        content_id: str,
        rule: object,
    ) -> None:
        """Remove uma regra de permissão específica de um conteúdo.

        ``rule`` deve ser um ``TSC.PermissionsRule`` com o grantee e capabilities
        a remover.
        """
        self._validate_content_type(content_type)
        endpoint, fetch_item = self._perm_dispatch[content_type]

        def op() -> None:
            item = fetch_item(content_id)
            self._check_view_show_tabs(content_type, item)
            endpoint.delete_permission(item, rule)

        self._with_reauth(op)

    # -- Default permissions (projetos) ----------------------------------------

    # Mapeamento de PermContentType → Resource string do TSC para default
    # permissions. Apenas tipos que suportam default permissions em projetos.
    _DEFAULT_PERM_RESOURCE_MAP: dict[PermContentType, str] = {
        PermContentType.workbook: "workbook",
        PermContentType.datasource: "datasource",
        PermContentType.flow: "flow",
        PermContentType.virtual_connection: "virtualConnection",
    }

    def get_default_permissions(
        self, project_id: str, content_type: PermContentType
    ) -> list[object]:
        """Obtém as permissões padrão de um projeto para um tipo de conteúdo.

        Retorna ``list[TSC.PermissionsRule]``. Suporta apenas tipos que possuem
        default permissions em projetos (workbook, datasource, flow,
        virtual_connection).
        """
        resource = self._DEFAULT_PERM_RESOURCE_MAP.get(content_type)
        if resource is None:
            raise TableauClientError(
                ErrorCode.VALIDATION_ERROR,
                f"Tipo '{content_type}' não suporta permissões padrão de projeto. "
                f"Tipos válidos: {', '.join(self._DEFAULT_PERM_RESOURCE_MAP.keys())}.",
            )

        def op() -> list[object]:
            project = self._server.projects.get_by_id(project_id)
            self._server.projects._default_permissions.populate_default_permissions(
                project, resource
            )
            # O TSC armazena como atributo dinâmico no projeto
            attr = f"_default_{resource}_permissions".lower()
            fetcher = getattr(project, attr, None)
            if fetcher is None:
                return []
            # O fetcher é uma callable que retorna a lista
            if callable(fetcher):
                return fetcher()
            return fetcher  # type: ignore[return-value]

        return self._with_reauth(op)

    def update_default_permissions(
        self,
        project_id: str,
        content_type: PermContentType,
        rules: list[object],
    ) -> list[object]:
        """Aplica regras de permissão padrão em um projeto para um tipo de conteúdo.

        Retorna a lista atualizada de ``TSC.PermissionsRule``.
        """
        resource = self._DEFAULT_PERM_RESOURCE_MAP.get(content_type)
        if resource is None:
            raise TableauClientError(
                ErrorCode.VALIDATION_ERROR,
                f"Tipo '{content_type}' não suporta permissões padrão de projeto. "
                f"Tipos válidos: {', '.join(self._DEFAULT_PERM_RESOURCE_MAP.keys())}.",
            )

        def op() -> list[object]:
            project = self._server.projects.get_by_id(project_id)
            dp = self._server.projects._default_permissions
            return dp.update_default_permissions(project, rules, resource)

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

"""Contratos Pydantic de saída das ferramentas MCP e envelope de erro tipado.

Cada ferramenta retorna **ou** seu modelo de sucesso (`status="success"`) **ou**
o envelope `ToolError` (`status="error"`). Campos ausentes no upstream (Tableau)
são normalizados para `None` (serializados como `null`).
"""

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Tipos compartilhados ----------------------------------------------------------

Severity = Literal["ok", "warning", "error"]
ContentType = Literal["workbook", "datasource"]


# Envelope de erro --------------------------------------------------------------


class ErrorCode(StrEnum):
    """Códigos de erro acionáveis expostos no envelope `ToolError`."""

    AUTH_FAILED = "AUTH_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    OVERWRITE_NOT_ALLOWED = "OVERWRITE_NOT_ALLOWED"
    INVALID_FILE = "INVALID_FILE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    RENDER_FAILED = "RENDER_FAILED"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    # Capacidade 5 — Hyper Datasources
    HYPER_INVALID_FILE = "HYPER_INVALID_FILE"
    HYPER_SCHEMA_MISMATCH = "HYPER_SCHEMA_MISMATCH"
    HYPER_SQL_ERROR = "HYPER_SQL_ERROR"
    DB_CONNECTION_NOT_CONFIGURED = "DB_CONNECTION_NOT_CONFIGURED"
    DB_CONNECTION_FAILED = "DB_CONNECTION_FAILED"
    DB_AUTH_FAILED = "DB_AUTH_FAILED"
    DB_QUERY_ERROR = "DB_QUERY_ERROR"
    # Capacidade 6 — Permissions
    LOCKED_PROJECT = "LOCKED_PROJECT"
    SHOW_TABS_ENABLED = "SHOW_TABS_ENABLED"


class ErrorDetail(BaseModel):
    """Detalhe do erro: código tipado + mensagem acionável (sem segredos)."""

    code: ErrorCode
    message: str


class ToolError(BaseModel):
    """Envelope de erro tipado retornado por qualquer ferramenta em caso de falha."""

    status: Literal["error"] = "error"
    error: ErrorDetail

    @classmethod
    def of(cls, code: ErrorCode, message: str) -> "ToolError":
        """Constrói um `ToolError` a partir de um código e mensagem.

        A mensagem deve ser acionável e nunca conter credenciais ou tokens.
        """
        return cls(error=ErrorDetail(code=code, message=message))


# Capacidade 1 — Deploy ---------------------------------------------------------


class PublishResult(BaseModel):
    """Resultado de publicação/sobrescrita de workbook ou datasource."""

    status: Literal["success"] = "success"
    content_id: str
    content_type: ContentType
    name: str
    project_id: str
    project_name: str
    mode: Literal["create_new", "overwrite"]
    chunked: bool
    webpage_url: str | None = None


# Capacidade 2 — Visual ---------------------------------------------------------


class VisualDiagnostic(BaseModel):
    """Veredito heurístico de erro visual (tela/gráfico em branco)."""

    is_likely_blank: bool
    blank_ratio: float
    severity: Severity
    message: str


class RenderImageResult(BaseModel):
    """Resultado da renderização PNG de uma view + diagnóstico visual.

    A imagem em si acompanha este JSON como bloco de imagem MCP.
    """

    status: Literal["success"] = "success"
    view_id: str
    mime_type: str = "image/png"
    applied_filters: dict[str, str] = Field(default_factory=dict)
    diagnostic: VisualDiagnostic
    # File-save metadata (populated when output_path is provided)
    output_path: str | None = None
    file_size_bytes: int | None = None
    save_error: str | None = None


class RenderPdfResult(BaseModel):
    """Resultado da renderização PDF de uma view.

    Quando `output_path` é fornecido, o PDF é salvo no disco e os campos de
    metadados de arquivo são preenchidos. A imagem inline acompanha como bloco
    File MCP quando `include_content=True`.
    """

    status: Literal["success"] = "success"
    view_id: str
    page_type: str
    mime_type: str = "application/pdf"
    # File-save metadata (populated when output_path is provided)
    output_path: str | None = None
    file_size_bytes: int | None = None
    save_error: str | None = None


# Capacidade 3 — QA estrutural --------------------------------------------------


class ConnectionInfo(BaseModel):
    """Conexão de dados declarada no workbook."""

    name: str
    type: str
    server: str | None = None
    is_valid: bool


class FieldInfo(BaseModel):
    """Campo do workbook (inclui calculados, com fórmula quando aplicável)."""

    name: str
    datatype: str
    role: str
    is_calculated: bool
    formula: str | None = None
    is_broken: bool = False


class FilterInfo(BaseModel):
    """Filtro declarado por worksheet."""

    worksheet: str
    worksheet_id: str | None = None
    field: str
    kind: str
    has_logic: bool


class StructureIssue(BaseModel):
    """Problema estrutural detectado (campo quebrado, filtro sem lógica, etc.)."""

    code: str
    severity: Severity
    target: str
    detail: str


class SheetRef(BaseModel):
    """Referência a uma worksheet ou dashboard com LUID renderizável.

    O campo `id` é o LUID da view aceito pelas ferramentas de render
    (`render_view_image`/`render_view_pdf`). Pode ser `null` quando a sheet não
    é uma view publicada (ex.: oculta) ou quando o enriquecimento via REST
    falhou; nesses casos o `name` é sempre preservado.
    """

    id: str | None = None
    name: str


class StructureReport(BaseModel):
    """Estrutura interna do workbook e problemas detectados (RF13/RF14)."""

    status: Literal["success"] = "success"
    workbook_id: str
    worksheets: list[SheetRef] = Field(default_factory=list)
    dashboards: list[SheetRef] = Field(default_factory=list)
    connections: list[ConnectionInfo] = Field(default_factory=list)
    fields: list[FieldInfo] = Field(default_factory=list)
    filters: list[FilterInfo] = Field(default_factory=list)
    issues: list[StructureIssue] = Field(default_factory=list)


class ComplexityMetrics(BaseModel):
    """Contagens medidas no workbook para auditoria de complexidade."""

    worksheets: int
    dashboards: int
    filters: int
    data_sources: int
    calculated_fields: int


class Thresholds(BaseModel):
    """Limiares de boas práticas usados na auditoria de complexidade."""

    max_filters: int
    max_worksheets: int
    max_data_sources: int


class ComplexityFinding(BaseModel):
    """Item que excedeu um limiar, com risco de performance associado."""

    metric: str
    value: int
    threshold: int
    severity: Severity
    recommendation: str


class ComplexityReport(BaseModel):
    """Auditoria de complexidade contra boas práticas (RF15/RF16)."""

    status: Literal["success"] = "success"
    workbook_id: str
    metrics: ComplexityMetrics
    thresholds: Thresholds
    compliant: bool
    findings: list[ComplexityFinding] = Field(default_factory=list)


# Capacidade 4 — Metadados ------------------------------------------------------


class ContentRef(BaseModel):
    """Referência atribuível a um conteúdo do Tableau."""

    id: str
    name: str
    type: ContentType
    project: str | None = None


class LineageNode(BaseModel):
    """Nó de dependência (ascendente/descendente) na linhagem."""

    id: str
    name: str
    type: str
    project: str | None = None
    owner: str | None = None


class LineageResult(BaseModel):
    """Linhagem ascendente ou descendente de um conteúdo (RF17/RF18)."""

    status: Literal["success"] = "success"
    direction: Literal["downstream", "upstream"]
    root: ContentRef
    dependencies: list[LineageNode] = Field(default_factory=list)


class DictionaryField(BaseModel):
    """Campo no dicionário de uma fonte de dados."""

    name: str
    datatype: str
    is_calculated: bool
    formula: str | None = None
    description: str | None = None


class DataDictionary(BaseModel):
    """Dicionário de campos de uma fonte de dados (RF19)."""

    status: Literal["success"] = "success"
    datasource_id: str
    datasource_name: str
    fields: list[DictionaryField] = Field(default_factory=list)


class SimilarityMatch(BaseModel):
    """Candidato similar encontrado na busca fuzzy."""

    id: str
    name: str
    type: ContentType
    project: str | None = None
    score: float


class SimilarityResult(BaseModel):
    """Resultado da busca de similaridade (RF20).

    `matches=[]` com `status="success"` significa nenhum semelhante encontrado —
    ausência de similar não é erro.
    """

    status: Literal["success"] = "success"
    query: str
    matches: list[SimilarityMatch] = Field(default_factory=list)


# Capacidade 5 — Hyper Datasources ----------------------------------------------

# Tipos escalares aceitos na definição de colunas inline; `numeric(p,s)` é
# validado à parte por regex (precisão/escala arbitrárias).
_INLINE_SCALAR_TYPES = frozenset(
    {"text", "big_int", "double", "bool", "date", "timestamp", "timestamp_tz"}
)
_NUMERIC_TYPE_RE = re.compile(r"^numeric\(\s*\d+\s*,\s*\d+\s*\)$")


class HyperColumn(BaseModel):
    """Coluna de uma tabela Hyper, com tipo lógico do contrato e nulabilidade."""

    name: str
    type: str
    nullable: bool


class InlineColumn(BaseModel):
    """Definição de coluna para dados inline (entrada).

    O `type` deve ser um dos tipos do contrato (`text`, `big_int`, `double`,
    `bool`, `date`, `timestamp`, `timestamp_tz`) ou `numeric(p,s)`. Tipos fora
    do contrato são rejeitados na validação.
    """

    name: str
    type: str
    nullable: bool = True

    @field_validator("type")
    @classmethod
    def _tipo_no_contrato(cls, value: str) -> str:
        if value in _INLINE_SCALAR_TYPES or _NUMERIC_TYPE_RE.match(value):
            return value
        aceitos = ", ".join(sorted(_INLINE_SCALAR_TYPES))
        raise ValueError(
            f"Tipo inline desconhecido: '{value}'. Use um de [{aceitos}] "
            "ou numeric(p,s)."
        )


class HyperCreateResult(BaseModel):
    """Relatório de criação/extração de um `.hyper` (RF4)."""

    status: Literal["success"] = "success"
    hyper_path: str
    table_name: str
    columns: list[HyperColumn] = Field(default_factory=list)
    row_count: int
    source: Literal["csv", "parquet", "inline", "database"]
    warnings: list[str] = Field(default_factory=list)


class HyperQueryResult(BaseModel):
    """Resultado de consulta SQL de leitura sobre um `.hyper` (RF13–RF14).

    `truncated=True` indica que o resultado foi cortado em `max_rows`; datas e
    timestamps chegam serializados como ISO-8601 e `numeric` como `str`.
    """

    status: Literal["success"] = "success"
    columns: list[HyperColumn] = Field(default_factory=list)
    rows: list[list[str | int | float | bool | None]] = Field(default_factory=list)
    row_count: int
    truncated: bool
    max_rows: int


class HyperTableInfo(BaseModel):
    """Descrição estrutural de uma tabela dentro de um `.hyper` (RF16).

    `row_count` é `None` quando a contagem não é determinável (ex.: falha ao
    contar linhas de uma tabela específica, sem abortar o relatório).
    """

    schema_name: str
    table_name: str
    columns: list[HyperColumn] = Field(default_factory=list)
    row_count: int | None


class HyperSchemaReport(BaseModel):
    """Relatório estrutural completo de um `.hyper` (RF16)."""

    status: Literal["success"] = "success"
    hyper_path: str
    file_size_bytes: int
    tables: list[HyperTableInfo] = Field(default_factory=list)


class HyperMutationResult(BaseModel):
    """Resultado de append/modificação sobre um `.hyper` (RF18–RF20).

    `affected_rows` é `None` para DDL sem contagem disponível; `table_name` é
    `None` quando a tabela alvo/criada não é identificável.
    """

    status: Literal["success"] = "success"
    hyper_path: str
    operation: Literal["append", "insert", "update", "delete", "create_table_as"]
    affected_rows: int | None
    table_name: str | None
    warnings: list[str] = Field(default_factory=list)


class ExceededDimension(BaseModel):
    """Dimensão de volume que excedeu o limiar configurado (RF23)."""

    dimension: Literal["source_file_mb", "inline_rows", "extracted_rows"]
    limit: float
    actual: float
    risk: str


class VolumeAlert(BaseModel):
    """Alerta estruturado não bloqueante de volume (RF23–RF24).

    Retornado no lugar do resultado quando uma dimensão pré-execução excede o
    limiar e `confirm_large_operation=False`. Não é erro: instrui o agente a
    repetir a chamada com confirmação explícita.
    """

    status: Literal["volume_alert"] = "volume_alert"
    exceeded: list[ExceededDimension] = Field(default_factory=list)
    message: str
    how_to_proceed: str


# Capacidade 6 — Permissions ---------------------------------------------------


class PermContentType(StrEnum):
    """Tipos de conteúdo suportados pelas ferramentas de permissão.

    Chave de dispatch para os métodos genéricos do `TableauClient` (ADR-003).
    Todos os valores são minúsculos e coincidem com o nome do membro.
    """

    project = "project"
    workbook = "workbook"
    datasource = "datasource"
    view = "view"
    flow = "flow"
    virtual_connection = "virtual_connection"


class CapabilityRule(BaseModel):
    """Uma capacidade e seu modo dentro de uma regra de permissão."""

    name: str  # ex.: "Read", "Write", "ExportData"
    mode: str  # "Allow" ou "Deny"


class GranteePermissions(BaseModel):
    """Conjunto de capacidades atribuídas a um usuário ou grupo (grantee)."""

    grantee_type: Literal["user", "group"]
    grantee_id: str
    grantee_name: str
    capabilities: list[CapabilityRule] = Field(default_factory=list)


class PermissionsResult(BaseModel):
    """Permissões explícitas de um item de conteúdo (RF grant/revoke/list)."""

    status: Literal["success"] = "success"
    content_type: str
    content_id: str
    content_name: str
    permissions: list[GranteePermissions] = Field(default_factory=list)


class DefaultPermissionsResult(BaseModel):
    """Permissões padrão de um projeto para um tipo de conteúdo específico."""

    status: Literal["success"] = "success"
    project_id: str
    project_name: str
    for_content_type: str
    permissions: list[GranteePermissions] = Field(default_factory=list)


class UserInfo(BaseModel):
    """Usuário do site com seu papel (site role)."""

    id: str
    name: str
    site_role: str
    last_login: str | None = None


class GroupInfo(BaseModel):
    """Grupo do site; `user_count` é `None` quando não informado pelo upstream."""

    id: str
    name: str
    user_count: int | None = None


class UserListResult(BaseModel):
    """Listagem de usuários resolvidos (RF list_users)."""

    status: Literal["success"] = "success"
    users: list[UserInfo] = Field(default_factory=list)
    total_count: int


class GroupListResult(BaseModel):
    """Listagem de grupos resolvidos (RF list_groups)."""

    status: Literal["success"] = "success"
    groups: list[GroupInfo] = Field(default_factory=list)
    total_count: int


class GroupMembersResult(BaseModel):
    """Membros de um grupo (RF list_group_members, somente leitura)."""

    status: Literal["success"] = "success"
    group_id: str
    group_name: str
    members: list[UserInfo] = Field(default_factory=list)


class ResolveResult(BaseModel):
    """Resolução de nome para LUID; `site_role` só se aplica a usuários."""

    status: Literal["success"] = "success"
    id: str
    name: str
    site_role: str | None = None  # apenas para usuários


class EffectiveCapability(BaseModel):
    """Modo efetivo de uma capacidade após aplicar as regras do Tableau."""

    name: str
    mode: Literal["Allow", "Deny"]
    # "user_rule", "group_rule", "site_role_cap", "ownership", "not_granted"
    reason: str


class EffectivePermissionsResult(BaseModel):
    """Acesso efetivo computado localmente para um usuário num conteúdo (ADR-002).

    Resultado "computado" (não autoritativo): combina regras explícitas,
    agregação de grupos (Deny-wins), teto do site role e overrides de
    propriedade/admin.
    """

    status: Literal["success"] = "success"
    content_type: str
    content_id: str
    user_id: str
    user_name: str
    site_role: str
    is_owner: bool
    is_admin: bool
    capabilities: list[EffectiveCapability] = Field(default_factory=list)
    summary: str  # legível, ex.: "Acesso nível Viewer (Read, Filter, ExportImage)"

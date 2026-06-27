"""Contratos Pydantic de saída das ferramentas MCP e envelope de erro tipado.

Cada ferramenta retorna **ou** seu modelo de sucesso (`status="success"`) **ou**
o envelope `ToolError` (`status="error"`). Campos ausentes no upstream (Tableau)
são normalizados para `None` (serializados como `null`).
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

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

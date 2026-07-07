"""Ferramentas MCP da Capacidade 2 (Visual): inspeção multimodal de views.

Ferramentas finas que orquestram a renderização via `TableauClient` e a
heurística pura `validation/visual.py`. `render_view_image` devolve o
`RenderImageResult` (JSON estruturado) **acompanhado do bloco de imagem MCP**
(`fastmcp.utilities.types.Image`) para consumo por agentes multimodais;
`render_workbook_pdf` devolve um status simples + o bloco de arquivo PDF
(`fastmcp.utilities.types.File`, `application/pdf`).

O veredito `diagnostic.severity == "error"` (tela em branco) sinaliza suspeita de
erro visual **sem** falhar a ferramenta: a imagem é sempre devolvida para
confirmação multimodal. O acesso ao Tableau acontece exclusivamente via
`tableau/client.py`; o registro no servidor é feito por `register(mcp)`.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from fastmcp.utilities.types import File, Image

from mcp_tableau.config import load_settings
from mcp_tableau.models import ErrorCode, RenderImageResult, ToolError
from mcp_tableau.tableau.client import TableauClientError, tableau_session
from mcp_tableau.tools._file_writer import atomic_write_bytes
from mcp_tableau.tools._validation import require_output_destination
from mcp_tableau.validation.visual import BlankRenderError, detect_blank_render


def render_view_image(
    view_id: str,
    filters: dict[str, str] | None = None,
    high_res: bool = True,
    output_path: str | None = None,
    include_content: bool = True,
    overwrite: bool = True,
) -> tuple[RenderImageResult, Image] | RenderImageResult | ToolError:
    """Renderiza o PNG de uma view e devolve diagnóstico + bloco de imagem MCP.

    Renderiza a view identificada por `view_id`, aplicando os `filters` como
    parâmetros `vf_` na requisição. Sobre os bytes aplica a heurística de tela em
    branco (`detect_blank_render`) e devolve o `RenderImageResult` (JSON) junto do
    bloco de imagem PNG para consumo multimodal. Uma tela provavelmente em branco
    (`diagnostic.severity == "error"`) **não** falha a ferramenta — a imagem é
    sempre devolvida para confirmação visual pelo agente.

    Quando `output_path` é fornecido, salva o PNG no caminho indicado usando
    escrita atômica. Se `include_content=False` (e `output_path` está definido),
    retorna apenas o `RenderImageResult` sem o bloco de imagem inline.

    Args:
        view_id: LUID da view a renderizar.
        filters: Pares campo→valor aplicados como `vf_` na renderização. Ausente
            ou `null` significa nenhum filtro.
        high_res: Quando `true`, solicita alta resolução ao Tableau.
        output_path: Caminho absoluto para salvar o PNG renderizado. Quando
            ausente/`null`, nenhum arquivo é gravado.
        include_content: Quando `true`, retorna o bloco de imagem MCP inline.
            Ignorado quando `output_path` não é fornecido (sempre retorna imagem).
        overwrite: Quando `true`, sobrescreve arquivo existente no `output_path`.
            Se `false` e o arquivo existir, retorna `ToolError(VALIDATION_ERROR)`
            sem chamar o Tableau.

    Returns:
        Tupla `(RenderImageResult, Image)` em caso de sucesso sem `output_path`,
        ou com `output_path` e `include_content=True`. Bare `RenderImageResult`
        quando `output_path` definido e `include_content=False`. `ToolError` com
        código acionável em caso de falha.
    """
    applied_filters = dict(filters) if filters else {}

    # --- Fail-fast overwrite check (before render) ---
    resolved_path: Path | None = None
    validation_error: ToolError | None = None

    if output_path is not None:
        resolved_path = Path(output_path).resolve()

        if not overwrite and resolved_path.exists():
            return ToolError.of(
                ErrorCode.VALIDATION_ERROR,
                f"File already exists at '{resolved_path}' and overwrite=false.",
            )

        # Validate extension and parent directory
        validation_error = require_output_destination(resolved_path, {".png"})

    # --- Tableau render ---
    try:
        with tableau_session(load_settings()) as client:
            png = client.render_view_image(view_id, applied_filters, high_res)
        diagnostic = detect_blank_render(png)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)
    except BlankRenderError as exc:
        return ToolError.of(ErrorCode.RENDER_FAILED, str(exc))

    # --- File write (only if path valid) ---
    save_error: str | None = None
    file_size_bytes: int | None = None
    written_path: str | None = None

    if resolved_path is not None:
        if validation_error is not None:
            save_error = validation_error.error.message
        else:
            try:
                file_size_bytes = atomic_write_bytes(resolved_path, png)
                written_path = str(resolved_path)
            except OSError as exc:
                save_error = str(exc)

    # --- Build result model ---
    result = RenderImageResult(
        view_id=view_id,
        applied_filters=applied_filters,
        diagnostic=diagnostic,
        output_path=written_path,
        file_size_bytes=file_size_bytes,
        save_error=save_error,
    )

    # --- Conditional return ---
    if output_path is not None and not include_content:
        return result
    return result, Image(data=png, format="png")


def render_workbook_pdf(
    view_id: str,
    filters: dict[str, str] | None = None,
    page_type: str = "A4",
) -> tuple[dict[str, str], File] | ToolError:
    """Renderiza o PDF de uma view e devolve status + bloco de arquivo PDF.

    Renderiza a view identificada por `view_id` como PDF no formato de página
    `page_type` (padrão `A4`), aplicando os `filters` como parâmetros `vf_`.
    Devolve um status simples (`{"status": "success", "view_id", "page_type"}`)
    acompanhado do bloco de arquivo PDF (`application/pdf`) para consumo pelo
    agente.

    Args:
        view_id: LUID da view a renderizar.
        filters: Pares campo→valor aplicados como `vf_` na renderização. Ausente
            ou `null` significa nenhum filtro.
        page_type: Formato de página do PDF (ex.: `A4`, `Letter`, `Tabloid`).

    Returns:
        Tupla `(status, File)` em caso de sucesso, ou `ToolError` com código
        acionável: `NOT_FOUND` (view inexistente), `RENDER_FAILED` ou demais
        códigos repassados do upstream.
    """
    applied_filters = dict(filters) if filters else {}

    try:
        with tableau_session(load_settings()) as client:
            pdf = client.render_view_pdf(view_id, page_type, applied_filters)
    except TableauClientError as exc:
        return ToolError.of(exc.code, exc.message)

    if not pdf:
        return ToolError.of(
            ErrorCode.RENDER_FAILED,
            "Render do PDF retornou vazio; nenhum conteúdo a devolver.",
        )

    status = {"status": "success", "view_id": view_id, "page_type": page_type}
    return status, File(data=pdf, format="pdf", name=view_id)


def register(mcp: FastMCP) -> None:
    """Registra as ferramentas de inspeção visual na instância FastMCP."""
    mcp.tool(render_view_image)
    mcp.tool(render_workbook_pdf)

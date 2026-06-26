"""Testes das ferramentas de inspeção visual (`tools/visual.py`).

Client Tableau e configuração são mockados; a heurística real (`detect_blank_render`)
opera sobre bytes PNG mínimos no caminho feliz e é substituída por monkeypatch nos
cenários de tela em branco e de render inválido.
"""

from __future__ import annotations

import contextlib
import io
from unittest.mock import MagicMock

import pytest
from fastmcp.utilities.types import File, Image
from PIL import Image as PILImage

from mcp_tableau.models import ErrorCode, RenderImageResult, ToolError, VisualDiagnostic
from mcp_tableau.tableau.client import TableauClientError
from mcp_tableau.tools import visual
from mcp_tableau.validation.visual import BlankRenderError


def _png_bytes(color: str = "white") -> bytes:
    """Gera um PNG 1x1 real para alimentar a heurística no caminho feliz."""
    buffer = io.BytesIO()
    PILImage.new("RGB", (1, 1), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def patched_session(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Substitui `tableau_session` e `load_settings` por mocks.

    Retorna o `client` mockado, cujos métodos de render os testes configuram.
    """
    client = MagicMock()

    @contextlib.contextmanager
    def fake_session(_settings: object):
        yield client

    monkeypatch.setattr(visual, "load_settings", lambda: object())
    monkeypatch.setattr(visual, "tableau_session", fake_session)
    return client


def test_render_view_image_sucesso_retorna_result_e_bloco_imagem(
    patched_session: MagicMock,
) -> None:
    patched_session.render_view_image.return_value = _png_bytes("white")

    result = visual.render_view_image("view-1")

    assert isinstance(result, tuple)
    payload, block = result
    assert isinstance(payload, RenderImageResult)
    assert isinstance(block, Image)
    assert payload.view_id == "view-1"
    assert payload.mime_type == "image/png"


def test_render_view_image_aplica_filtros_vf_no_request_options(
    patched_session: MagicMock,
) -> None:
    patched_session.render_view_image.return_value = _png_bytes("white")
    filters = {"Region": "West", "Year": "2026"}

    result = visual.render_view_image("view-1", filters=filters, high_res=False)

    payload, _ = result
    patched_session.render_view_image.assert_called_once_with("view-1", filters, False)
    assert payload.applied_filters == filters


def test_render_view_image_tela_em_branco_define_severity_error_sem_falhar(
    patched_session: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    patched_session.render_view_image.return_value = _png_bytes("white")
    blank = VisualDiagnostic(
        is_likely_blank=True,
        blank_ratio=1.0,
        severity="error",
        message="Render provavelmente em branco.",
    )
    monkeypatch.setattr(visual, "detect_blank_render", lambda _png: blank)

    result = visual.render_view_image("view-1")

    assert isinstance(result, tuple)
    payload, block = result
    assert isinstance(payload, RenderImageResult)
    assert isinstance(block, Image)
    assert payload.diagnostic.severity == "error"


def test_render_view_image_view_inexistente_retorna_not_found(
    patched_session: MagicMock,
) -> None:
    patched_session.render_view_image.side_effect = TableauClientError(
        ErrorCode.NOT_FOUND, "Recurso não encontrado no Tableau."
    )

    result = visual.render_view_image("missing")

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.NOT_FOUND


def test_render_view_image_falha_render_retorna_render_failed(
    patched_session: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    patched_session.render_view_image.return_value = b"not-a-png"

    def _raise(_png: bytes) -> VisualDiagnostic:
        raise BlankRenderError("Bytes de imagem inválidos ou ilegíveis.")

    monkeypatch.setattr(visual, "detect_blank_render", _raise)

    result = visual.render_view_image("view-1")

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.RENDER_FAILED


def test_render_workbook_pdf_sucesso_retorna_bloco_pdf(
    patched_session: MagicMock,
) -> None:
    patched_session.render_view_pdf.return_value = b"%PDF-1.4 fake"

    result = visual.render_workbook_pdf("view-1")

    assert isinstance(result, tuple)
    status, block = result
    assert isinstance(block, File)
    assert status == {
        "status": "success",
        "view_id": "view-1",
        "page_type": "A4",
    }


def test_render_workbook_pdf_page_type_default_a4(
    patched_session: MagicMock,
) -> None:
    patched_session.render_view_pdf.return_value = b"%PDF-1.4 fake"

    visual.render_workbook_pdf("view-1", filters={"Region": "West"})

    patched_session.render_view_pdf.assert_called_once_with(
        "view-1", "A4", {"Region": "West"}
    )

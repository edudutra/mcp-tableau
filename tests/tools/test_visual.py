"""Testes das ferramentas de inspeção visual (`tools/visual.py`).

Client Tableau e configuração são mockados; a heurística real (`detect_blank_render`)
opera sobre bytes PNG mínimos no caminho feliz e é substituída por monkeypatch nos
cenários de tela em branco e de render inválido.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastmcp.utilities.types import File, Image
from PIL import Image as PILImage

from mcp_tableau.models import (
    ErrorCode,
    RenderImageResult,
    RenderPdfResult,
    ToolError,
    VisualDiagnostic,
)
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


# ===========================================================================
# render_view_image — File-save scenarios
# ===========================================================================


class TestRenderViewImageFileSave:
    """Tests for the file-save logic in render_view_image."""

    def test_output_path_none_behavior_unchanged(
        self, patched_session: MagicMock
    ) -> None:
        """output_path=None → existing behavior: tuple returned, no file on disk."""
        patched_session.render_view_image.return_value = _png_bytes("blue")

        result = visual.render_view_image("view-1")

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(payload, RenderImageResult)
        assert isinstance(block, Image)
        assert payload.output_path is None
        assert payload.file_size_bytes is None
        assert payload.save_error is None

    def test_output_path_valid_include_content_true_returns_tuple_and_writes_file(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """output_path valid + include_content=true → tuple + file written."""
        png = _png_bytes("red")
        patched_session.render_view_image.return_value = png
        dest = tmp_path / "render.png"

        result = visual.render_view_image(
            "view-1", output_path=str(dest), include_content=True
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(payload, RenderImageResult)
        assert isinstance(block, Image)
        assert payload.output_path == str(dest.resolve())
        assert payload.file_size_bytes == len(png)
        assert payload.save_error is None
        assert dest.read_bytes() == png

    def test_output_path_valid_include_content_false_returns_bare_model(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """output_path valid + include_content=false → bare model + file."""
        png = _png_bytes("green")
        patched_session.render_view_image.return_value = png
        dest = tmp_path / "render.png"

        result = visual.render_view_image(
            "view-1", output_path=str(dest), include_content=False
        )

        assert isinstance(result, RenderImageResult)
        assert not isinstance(result, tuple)
        assert result.output_path == str(dest.resolve())
        assert result.file_size_bytes == len(png)
        assert result.save_error is None
        assert dest.read_bytes() == png

    def test_output_path_wrong_extension_sets_save_error_and_returns_tuple(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """Wrong extension (.pdf) → render succeeds, save_error set."""
        png = _png_bytes("white")
        patched_session.render_view_image.return_value = png
        dest = tmp_path / "render.pdf"

        result = visual.render_view_image(
            "view-1", output_path=str(dest), include_content=True
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(block, Image)
        assert payload.save_error is not None
        assert ".pdf" in payload.save_error
        assert payload.output_path is None
        assert payload.file_size_bytes is None
        assert not dest.exists()

    def test_output_path_missing_parent_dir_sets_save_error(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """Missing parent directory → render succeeds, save_error set."""
        png = _png_bytes("white")
        patched_session.render_view_image.return_value = png
        dest = tmp_path / "nonexistent" / "render.png"

        result = visual.render_view_image(
            "view-1", output_path=str(dest), include_content=True
        )

        assert isinstance(result, tuple)
        payload, _ = result
        assert payload.save_error is not None
        assert "does not exist" in payload.save_error
        assert payload.output_path is None
        assert payload.file_size_bytes is None

    def test_overwrite_false_file_exists_returns_tool_error_no_render(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """overwrite=false + exists → ToolError(VALIDATION_ERROR)."""
        dest = tmp_path / "existing.png"
        dest.write_bytes(b"old content")

        result = visual.render_view_image(
            "view-1", output_path=str(dest), overwrite=False
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "overwrite=false" in result.error.message
        patched_session.render_view_image.assert_not_called()
        # File content unchanged
        assert dest.read_bytes() == b"old content"

    def test_overwrite_true_file_exists_overwrites_file(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """overwrite=true + file exists → file overwritten, success."""
        png = _png_bytes("blue")
        patched_session.render_view_image.return_value = png
        dest = tmp_path / "existing.png"
        dest.write_bytes(b"old content")

        result = visual.render_view_image(
            "view-1", output_path=str(dest), overwrite=True
        )

        assert isinstance(result, tuple)
        payload, _ = result
        assert payload.output_path == str(dest.resolve())
        assert payload.file_size_bytes == len(png)
        assert payload.save_error is None
        assert dest.read_bytes() == png

    def test_write_failure_oserror_sets_save_error_returns_inline_content(
        self,
        patched_session: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Write failure (OSError) → save_error set, inline content still returned."""
        png = _png_bytes("white")
        patched_session.render_view_image.return_value = png
        dest = tmp_path / "render.png"

        def _raise_oserror(path, data):
            raise OSError("Permission denied")

        monkeypatch.setattr(visual, "atomic_write_bytes", _raise_oserror)

        result = visual.render_view_image(
            "view-1", output_path=str(dest), include_content=True
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(block, Image)
        assert payload.save_error == "Permission denied"
        assert payload.output_path is None
        assert payload.file_size_bytes is None

    def test_include_content_ignored_when_output_path_is_none(
        self, patched_session: MagicMock
    ) -> None:
        """include_content ignored when output_path is None."""
        patched_session.render_view_image.return_value = _png_bytes("white")

        result = visual.render_view_image(
            "view-1", output_path=None, include_content=False
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(payload, RenderImageResult)
        assert isinstance(block, Image)

    def test_file_content_on_disk_matches_png_bytes(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """File content on disk matches the exact PNG bytes from Tableau render."""
        png = _png_bytes("red")
        patched_session.render_view_image.return_value = png
        dest = tmp_path / "output.png"

        visual.render_view_image("view-1", output_path=str(dest))

        assert dest.read_bytes() == png

    def test_end_to_end_mocked_session_render_save_verify(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """End-to-end: mocked session — render + save + verify."""
        png = _png_bytes("blue")
        patched_session.render_view_image.return_value = png
        dest = tmp_path / "integration_test.png"

        result = visual.render_view_image(
            "view-1",
            filters={"Region": "East"},
            high_res=True,
            output_path=str(dest),
            include_content=True,
            overwrite=True,
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert payload.view_id == "view-1"
        assert payload.applied_filters == {"Region": "East"}
        assert payload.output_path == str(dest.resolve())
        assert payload.file_size_bytes == len(png)
        assert payload.save_error is None
        assert payload.diagnostic is not None
        assert isinstance(block, Image)
        assert dest.read_bytes() == png
        patched_session.render_view_image.assert_called_once_with(
            "view-1", {"Region": "East"}, True
        )


# ===========================================================================
# render_workbook_pdf
# ===========================================================================


def test_render_workbook_pdf_sucesso_retorna_bloco_pdf(
    patched_session: MagicMock,
) -> None:
    patched_session.render_view_pdf.return_value = b"%PDF-1.4 fake"

    result = visual.render_workbook_pdf("view-1")

    assert isinstance(result, tuple)
    payload, block = result
    assert isinstance(payload, RenderPdfResult)
    assert isinstance(block, File)
    assert payload.status == "success"
    assert payload.view_id == "view-1"
    assert payload.page_type == "A4"
    assert payload.mime_type == "application/pdf"
    assert payload.output_path is None
    assert payload.file_size_bytes is None
    assert payload.save_error is None


def test_render_workbook_pdf_page_type_default_a4(
    patched_session: MagicMock,
) -> None:
    patched_session.render_view_pdf.return_value = b"%PDF-1.4 fake"

    visual.render_workbook_pdf("view-1", filters={"Region": "West"})

    patched_session.render_view_pdf.assert_called_once_with(
        "view-1", "A4", {"Region": "West"}
    )


# ===========================================================================
# render_workbook_pdf — File-save scenarios
# ===========================================================================


class TestRenderWorkbookPdfFileSave:
    """Tests for the file-save logic in render_workbook_pdf."""

    def test_output_path_none_behavior_unchanged(
        self, patched_session: MagicMock
    ) -> None:
        """output_path=None → existing behavior: tuple returned, no file on disk."""
        patched_session.render_view_pdf.return_value = b"%PDF-1.4 fake"

        result = visual.render_workbook_pdf("view-1")

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(payload, RenderPdfResult)
        assert isinstance(block, File)
        assert payload.output_path is None
        assert payload.file_size_bytes is None
        assert payload.save_error is None

    def test_output_path_valid_include_content_true_returns_tuple_and_writes_file(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """output_path valid + include_content=true → tuple returned + file written."""
        pdf_data = b"%PDF-1.4 test content"
        patched_session.render_view_pdf.return_value = pdf_data
        dest = tmp_path / "render.pdf"

        result = visual.render_workbook_pdf(
            "view-1", output_path=str(dest), include_content=True
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(payload, RenderPdfResult)
        assert isinstance(block, File)
        assert payload.output_path == str(dest.resolve())
        assert payload.file_size_bytes == len(pdf_data)
        assert payload.save_error is None
        assert dest.read_bytes() == pdf_data

    def test_output_path_valid_include_content_false_returns_bare_model(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """output_path valid + include_content=false → bare RenderPdfResult + file."""
        pdf_data = b"%PDF-1.4 bare model test"
        patched_session.render_view_pdf.return_value = pdf_data
        dest = tmp_path / "render.pdf"

        result = visual.render_workbook_pdf(
            "view-1", output_path=str(dest), include_content=False
        )

        assert isinstance(result, RenderPdfResult)
        assert not isinstance(result, tuple)
        assert result.output_path == str(dest.resolve())
        assert result.file_size_bytes == len(pdf_data)
        assert result.save_error is None
        assert dest.read_bytes() == pdf_data

    def test_output_path_wrong_extension_sets_save_error_and_returns_tuple(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """Wrong extension (.png) → render succeeds, save_error set, tuple returned."""
        pdf_data = b"%PDF-1.4 wrong ext"
        patched_session.render_view_pdf.return_value = pdf_data
        dest = tmp_path / "render.png"

        result = visual.render_workbook_pdf(
            "view-1", output_path=str(dest), include_content=True
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(block, File)
        assert payload.save_error is not None
        assert ".png" in payload.save_error
        assert payload.output_path is None
        assert payload.file_size_bytes is None
        assert not dest.exists()

    def test_output_path_missing_parent_dir_sets_save_error(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """Missing parent directory → render succeeds, save_error set."""
        pdf_data = b"%PDF-1.4 missing parent"
        patched_session.render_view_pdf.return_value = pdf_data
        dest = tmp_path / "nonexistent" / "render.pdf"

        result = visual.render_workbook_pdf(
            "view-1", output_path=str(dest), include_content=True
        )

        assert isinstance(result, tuple)
        payload, _ = result
        assert payload.save_error is not None
        assert "does not exist" in payload.save_error
        assert payload.output_path is None
        assert payload.file_size_bytes is None

    def test_overwrite_false_file_exists_returns_tool_error_no_render(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """overwrite=false + file exists → ToolError(VALIDATION_ERROR), no render."""
        dest = tmp_path / "existing.pdf"
        dest.write_bytes(b"old PDF content")

        result = visual.render_workbook_pdf(
            "view-1", output_path=str(dest), overwrite=False
        )

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.VALIDATION_ERROR
        assert "overwrite=false" in result.error.message
        patched_session.render_view_pdf.assert_not_called()
        # File content unchanged
        assert dest.read_bytes() == b"old PDF content"

    def test_overwrite_true_file_exists_overwrites_file(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """overwrite=true + file exists → file overwritten, success."""
        pdf_data = b"%PDF-1.4 new content"
        patched_session.render_view_pdf.return_value = pdf_data
        dest = tmp_path / "existing.pdf"
        dest.write_bytes(b"old PDF content")

        result = visual.render_workbook_pdf(
            "view-1", output_path=str(dest), overwrite=True
        )

        assert isinstance(result, tuple)
        payload, _ = result
        assert payload.output_path == str(dest.resolve())
        assert payload.file_size_bytes == len(pdf_data)
        assert payload.save_error is None
        assert dest.read_bytes() == pdf_data

    def test_write_failure_oserror_sets_save_error_returns_inline_content(
        self,
        patched_session: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Write failure (OSError) → save_error set, inline content still returned."""
        pdf_data = b"%PDF-1.4 oserror test"
        patched_session.render_view_pdf.return_value = pdf_data
        dest = tmp_path / "render.pdf"

        def _raise_oserror(path, data):
            raise OSError("Permission denied")

        monkeypatch.setattr(visual, "atomic_write_bytes", _raise_oserror)

        result = visual.render_workbook_pdf(
            "view-1", output_path=str(dest), include_content=True
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(block, File)
        assert payload.save_error == "Permission denied"
        assert payload.output_path is None
        assert payload.file_size_bytes is None

    def test_empty_pdf_from_tableau_returns_render_failed(
        self, patched_session: MagicMock
    ) -> None:
        """Empty PDF from Tableau → ToolError(RENDER_FAILED) (existing behavior)."""
        patched_session.render_view_pdf.return_value = b""

        result = visual.render_workbook_pdf("view-1")

        assert isinstance(result, ToolError)
        assert result.error.code == ErrorCode.RENDER_FAILED

    def test_result_has_correct_view_id_page_type_and_mime_type(
        self, patched_session: MagicMock
    ) -> None:
        """RenderPdfResult has correct view_id, page_type, and mime_type fields."""
        patched_session.render_view_pdf.return_value = b"%PDF-1.4 fields"

        result = visual.render_workbook_pdf("view-42", page_type="Letter")

        assert isinstance(result, tuple)
        payload, _ = result
        assert payload.view_id == "view-42"
        assert payload.page_type == "Letter"
        assert payload.mime_type == "application/pdf"

    def test_file_content_on_disk_matches_pdf_bytes(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """File content on disk matches the exact PDF bytes from Tableau render."""
        pdf_data = b"%PDF-1.4 exact match test"
        patched_session.render_view_pdf.return_value = pdf_data
        dest = tmp_path / "output.pdf"

        visual.render_workbook_pdf("view-1", output_path=str(dest))

        assert dest.read_bytes() == pdf_data

    def test_include_content_ignored_when_output_path_is_none(
        self, patched_session: MagicMock
    ) -> None:
        """include_content=False ignored when output_path is None → tuple returned."""
        patched_session.render_view_pdf.return_value = b"%PDF-1.4 ignore"

        result = visual.render_workbook_pdf(
            "view-1", output_path=None, include_content=False
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert isinstance(payload, RenderPdfResult)
        assert isinstance(block, File)

    def test_end_to_end_mocked_session_render_save_verify(
        self, patched_session: MagicMock, tmp_path: Path
    ) -> None:
        """End-to-end: mocked session — render + save + verify file content."""
        pdf_data = b"%PDF-1.4 integration test content"
        patched_session.render_view_pdf.return_value = pdf_data
        dest = tmp_path / "integration_test.pdf"

        result = visual.render_workbook_pdf(
            "view-1",
            filters={"Region": "East"},
            page_type="Tabloid",
            output_path=str(dest),
            include_content=True,
            overwrite=True,
        )

        assert isinstance(result, tuple)
        payload, block = result
        assert payload.view_id == "view-1"
        assert payload.page_type == "Tabloid"
        assert payload.mime_type == "application/pdf"
        assert payload.output_path == str(dest.resolve())
        assert payload.file_size_bytes == len(pdf_data)
        assert payload.save_error is None
        assert isinstance(block, File)
        assert dest.read_bytes() == pdf_data
        patched_session.render_view_pdf.assert_called_once_with(
            "view-1", "Tabloid", {"Region": "East"}
        )

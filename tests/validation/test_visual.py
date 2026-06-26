"""Testes da heurística de render em branco pura (`validation/visual.py`)."""

from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw

from mcp_tableau.validation.visual import BlankRenderError, detect_blank_render


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _solid(color: str = "white", size: tuple[int, int] = (60, 60)) -> bytes:
    return _png(Image.new("RGB", size, color))


def _with_content(size: tuple[int, int] = (60, 60)) -> bytes:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    # Cobre boa parte da área com cores variadas para baixar a uniformidade.
    draw.rectangle([2, 2, 58, 30], fill="red")
    draw.rectangle([2, 31, 58, 58], fill="blue")
    draw.ellipse([15, 15, 45, 45], fill="green")
    return _png(image)


def test_detect_blank_render_imagem_uniforme_branca_is_likely_blank_true() -> None:
    diagnostic = detect_blank_render(_solid("white"))

    assert diagnostic.is_likely_blank is True
    assert diagnostic.blank_ratio == 1.0
    assert diagnostic.severity == "error"


def test_detect_blank_render_imagem_com_conteudo_is_likely_blank_false() -> None:
    diagnostic = detect_blank_render(_with_content())

    assert diagnostic.is_likely_blank is False
    assert diagnostic.blank_ratio < 0.95


@pytest.mark.parametrize(
    "image_bytes",
    [
        _solid("white"),
        _solid("black"),
        _with_content(),
        _png(Image.new("RGBA", (40, 40), (0, 0, 0, 0))),
    ],
)
def test_detect_blank_render_blank_ratio_entre_zero_e_um(image_bytes: bytes) -> None:
    diagnostic = detect_blank_render(image_bytes)

    assert 0.0 <= diagnostic.blank_ratio <= 1.0


@pytest.mark.parametrize(
    ("blank_threshold", "expected_severity"),
    [
        (0.95, "error"),  # imagem 100% uniforme excede o limiar
        (1.0, "error"),  # ratio 1.0 atinge o limiar 1.0
    ],
)
def test_detect_blank_render_severity_error_quando_acima_do_limiar(
    blank_threshold: float, expected_severity: str
) -> None:
    diagnostic = detect_blank_render(_solid("white"), blank_threshold=blank_threshold)

    assert diagnostic.severity == expected_severity
    assert diagnostic.is_likely_blank is True


def test_detect_blank_render_limiar_alto_imagem_com_conteudo_nao_e_erro() -> None:
    # Com limiar baixo, conteúdo variado fica abaixo => não é erro.
    diagnostic = detect_blank_render(_with_content(), blank_threshold=0.99)

    assert diagnostic.is_likely_blank is False
    assert diagnostic.severity != "error"


@pytest.mark.parametrize("payload", [b"", b"isto nao e uma imagem", b"\x89PNGquebrado"])
def test_detect_blank_render_bytes_invalidos_levanta_erro_tratavel(
    payload: bytes,
) -> None:
    with pytest.raises(BlankRenderError):
        detect_blank_render(payload)

"""Heurística pura de detecção de render em branco a partir dos bytes da imagem.

`detect_blank_render` decide se uma imagem PNG renderizada de uma view do Tableau
está provavelmente "em branco" (uniforme/sem conteúdo). A métrica `blank_ratio` é
a fração de pixels que pertencem à cor dominante — quanto mais perto de 1.0, mais
uniforme (logo, mais provavelmente em branco). É pura: opera só sobre os bytes.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

from mcp_tableau.models import VisualDiagnostic

# Acima deste limiar de uniformidade, o render é considerado em branco com
# severidade de erro. Configurável por chamada.
DEFAULT_BLANK_THRESHOLD = 0.95

# Faixa de tolerância entre "claramente com conteúdo" e o limiar de erro:
# nessa zona sinalizamos como `warning` (suspeita), sem afirmar erro.
_WARNING_MARGIN = 0.05


class BlankRenderError(Exception):
    """Erro tratável quando os bytes não formam uma imagem decodificável."""


def detect_blank_render(
    image_bytes: bytes, blank_threshold: float = DEFAULT_BLANK_THRESHOLD
) -> VisualDiagnostic:
    """Avalia se o PNG renderizado está provavelmente em branco.

    Args:
        image_bytes: Conteúdo binário da imagem (tipicamente PNG).
        blank_threshold: Uniformidade mínima (0–1) para classificar como em
            branco com severidade `error`. Padrão `0.95`.

    Returns:
        `VisualDiagnostic` com `blank_ratio` sempre em [0.0, 1.0], `is_likely_blank`
        e `severity` derivados do limiar, e uma `message` explicativa.

    Raises:
        BlankRenderError: Se os bytes estiverem vazios ou não decodificarem como
            imagem válida.
    """
    if not image_bytes:
        raise BlankRenderError("Nenhum byte de imagem fornecido para diagnóstico.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            blank_ratio = _dominant_color_ratio(image)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise BlankRenderError(
            f"Bytes de imagem inválidos ou ilegíveis. Detalhe: {exc}"
        ) from exc

    # Salvaguarda numérica: blank_ratio NUNCA escapa de [0.0, 1.0].
    blank_ratio = min(1.0, max(0.0, blank_ratio))

    is_likely_blank = blank_ratio >= blank_threshold
    severity, message = _classify(blank_ratio, blank_threshold)

    return VisualDiagnostic(
        is_likely_blank=is_likely_blank,
        blank_ratio=blank_ratio,
        severity=severity,
        message=message,
    )


def _dominant_color_ratio(image: Image.Image) -> float:
    """Retorna a fração de pixels pertencentes à cor mais frequente.

    Converte para RGB para tratar canais alfa/paleta de forma uniforme. Usa o
    histograma de cores; quando há cores demais para contar (imagem rica), a
    cor dominante cobre uma fração pequena e o ratio tende a 0.
    """
    rgb = image.convert("RGB")
    total = rgb.width * rgb.height
    if total == 0:
        return 1.0

    # maxcolors alto garante contagem exata mesmo para imagens variadas;
    # se estourar, getcolors retorna None e tratamos como não-uniforme.
    colors = rgb.getcolors(maxcolors=total)
    if not colors:
        return 0.0

    dominant_count = max(count for count, _ in colors)
    return dominant_count / total


def _classify(blank_ratio: float, blank_threshold: float) -> tuple[str, str]:
    """Mapeia o ratio para `severity` e mensagem acionável."""
    if blank_ratio >= blank_threshold:
        return (
            "error",
            (
                f"Render provavelmente em branco: {blank_ratio:.0%} dos pixels são "
                "de uma única cor."
            ),
        )

    if blank_ratio >= blank_threshold - _WARNING_MARGIN:
        return (
            "warning",
            (
                f"Render quase uniforme ({blank_ratio:.0%} da cor dominante); "
                "pode haver pouco conteúdo visível."
            ),
        )

    return (
        "ok",
        f"Render com conteúdo: cor dominante cobre {blank_ratio:.0%} dos pixels.",
    )

"""Validadores compartilhados da camada de ferramentas MCP.

Módulo interno (prefixo `_`) que concentra validações puras reutilizáveis entre
as ferramentas de `tools/`. Sem I/O de rede e sem dependência do cliente
Tableau — apenas checagens locais baratas sobre caminhos de saída. É a fonte
única de verdade da validação de destino de escrita (ADR-003), consumida pelas
ferramentas visuais e de Hyper.
"""

from __future__ import annotations

from pathlib import Path

from mcp_tableau.models import ErrorCode, ToolError


def require_output_destination(
    path: Path,
    allowed_suffixes: set[str],
) -> ToolError | None:
    """Valida um caminho de destino de escrita: extensão e diretório-pai.

    Generaliza o padrão de `_require_hyper_destination` (hyper.py) para qualquer
    conjunto de extensões permitidas. Não exige que o arquivo já exista (ele será
    criado/sobrescrito); um destino inválido é erro de parâmetro
    (`VALIDATION_ERROR`), não de arquivo.

    A comparação de extensão é case-insensitive: `path.suffix` é normalizado para
    minúsculas antes de checar contra `allowed_suffixes` (que deve conter as
    extensões já em minúsculas, ex.: `{".png", ".jpg"}`). A extensão é checada
    antes do diretório-pai — quando ambos falham, o erro de extensão prevalece.

    Args:
        path: Caminho de destino do arquivo a ser escrito.
        allowed_suffixes: Extensões aceitas, em minúsculas e com ponto
            (ex.: `{".png"}`, `{".png", ".jpg"}`).

    Returns:
        `None` quando o destino é válido, ou `ToolError` com `VALIDATION_ERROR`
        — citando o caminho, a extensão encontrada e as esperadas, ou o
        diretório-pai inexistente — em caso de falha.
    """
    suffix = path.suffix.lower()
    if suffix not in allowed_suffixes:
        expected = ", ".join(sorted(allowed_suffixes))
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"O caminho de saída '{path}' tem extensão '{suffix}'; "
            f"esperado: {expected}.",
        )
    if not path.parent.is_dir():
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"O diretório-pai '{path.parent}' não existe.",
        )
    return None

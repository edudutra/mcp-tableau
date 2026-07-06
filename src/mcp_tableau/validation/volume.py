"""Salvaguardas puras de volume das operações Hyper (RF23–RF25).

Avaliam dimensões de volume (tamanho do arquivo de origem, linhas inline, linhas
extraídas) contra os limiares de `Settings` e produzem a lista de dimensões
excedidas usada por `VolumeAlert` e por `warnings`. São funções puras: não
acessam rede nem fazem IO além de `Path.stat()` no arquivo de origem.

Comparação estrita (`>`): um valor exatamente igual ao limiar NÃO excede.
"""

from __future__ import annotations

from pathlib import Path

from mcp_tableau.config import Settings
from mcp_tableau.models import ExceededDimension

# 1 MB = 1024 * 1024 bytes (binário), coerente com o tamanho lógico em disco.
_BYTES_PER_MB = 1024 * 1024

_SOURCE_FILE_RISK = (
    "Arquivo de origem grande pode esgotar disco local e alongar o processamento."
)
_INLINE_ROWS_RISK = (
    "Volume alto de linhas inline pode consumir memória; prefira "
    "create_hyper_from_file para grandes cargas."
)
_EXTRACTED_ROWS_RISK = (
    "Volume extraído grande pode esgotar disco local; valide o espaço "
    "disponível antes de repetir operações desse porte."
)


def check_source_file(path: Path, settings: Settings) -> list[ExceededDimension]:
    """Avalia o tamanho do arquivo de origem contra `HYPER_MAX_SOURCE_FILE_MB`.

    Retorna a dimensão `source_file_mb` quando o arquivo excede estritamente o
    limiar; caso contrário, lista vazia. Faz apenas `stat` do caminho informado.
    """
    size_mb = path.stat().st_size / _BYTES_PER_MB
    limit = settings.hyper_max_source_file_mb
    if size_mb > limit:
        return [
            ExceededDimension(
                dimension="source_file_mb",
                limit=float(limit),
                actual=round(size_mb, 1),
                risk=_SOURCE_FILE_RISK,
            )
        ]
    return []


def check_inline_rows(row_count: int, settings: Settings) -> list[ExceededDimension]:
    """Avalia a quantidade de linhas inline contra `HYPER_MAX_INLINE_ROWS`.

    Retorna a dimensão `inline_rows` quando `row_count` excede estritamente o
    limiar; caso contrário, lista vazia.
    """
    limit = settings.hyper_max_inline_rows
    if row_count > limit:
        return [
            ExceededDimension(
                dimension="inline_rows",
                limit=float(limit),
                actual=float(row_count),
                risk=_INLINE_ROWS_RISK,
            )
        ]
    return []


def check_extracted_rows(row_count: int, settings: Settings) -> list[ExceededDimension]:
    """Avalia as linhas extraídas de um banco contra `HYPER_MAX_EXTRACT_ROWS`.

    Retorna a dimensão `extracted_rows` quando `row_count` excede estritamente o
    limiar; caso contrário, lista vazia. Usada pós-execução (o volume só é
    conhecido após a extração), alimentando `warnings` do resultado.
    """
    limit = settings.hyper_max_extract_rows
    if row_count > limit:
        return [
            ExceededDimension(
                dimension="extracted_rows",
                limit=float(limit),
                actual=float(row_count),
                risk=_EXTRACTED_ROWS_RISK,
            )
        ]
    return []

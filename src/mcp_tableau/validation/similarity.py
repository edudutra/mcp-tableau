"""Ranking fuzzy puro de conteúdo similar por nome.

`rank_similar` ordena candidatos por semelhança ao termo de busca, do maior para
o menor score. A comparação é insensível a maiúsculas/minúsculas e a acentos
(normalização Unicode). Score na escala 0.0–1.0, consistente com
`SimilarityMatch.score` (match exato normalizado = 1.0). É pura: sem rede.
"""

from __future__ import annotations

import unicodedata

from rapidfuzz import fuzz

from mcp_tableau.models import ContentRef, SimilarityMatch


def rank_similar(
    term: str,
    candidates: list[ContentRef],
    limit: int = 10,
) -> list[SimilarityMatch]:
    """Classifica candidatos por similaridade fuzzy de nome ao `term`.

    Args:
        term: Termo de busca.
        candidates: Conteúdos candidatos a comparar.
        limit: Número máximo de resultados retornados (os de maior score).

    Returns:
        Lista de `SimilarityMatch` ordenada por `score` decrescente (escala
        0.0–1.0; match exato normalizado = 1.0), respeitando `limit`. Lista vazia
        quando não há candidatos ou `limit <= 0`.
    """
    if not candidates or limit <= 0:
        return []

    normalized_term = _normalize(term)

    scored: list[SimilarityMatch] = []
    for candidate in candidates:
        score = fuzz.WRatio(normalized_term, _normalize(candidate.name)) / 100.0
        scored.append(
            SimilarityMatch(
                id=candidate.id,
                name=candidate.name,
                type=candidate.type,
                project=candidate.project,
                score=score,
            )
        )

    # Ordena por score decrescente; desempate estável por nome para determinismo.
    scored.sort(key=lambda match: (-match.score, match.name))
    return scored[:limit]


def _normalize(value: str) -> str:
    """Normaliza para comparação: minúsculas e sem acentos (NFKD sem combinantes)."""
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip()

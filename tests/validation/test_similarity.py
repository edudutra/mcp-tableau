"""Testes do ranking fuzzy de similaridade puro (`validation/similarity.py`)."""

from __future__ import annotations

from mcp_tableau.models import ContentRef
from mcp_tableau.validation.similarity import rank_similar


def _ref(id_: str, name: str, type_: str = "workbook") -> ContentRef:
    return ContentRef(id=id_, name=name, type=type_)  # type: ignore[arg-type]


def test_rank_similar_ordena_por_score_decrescente() -> None:
    candidates = [
        _ref("1", "Estoque Geral", "datasource"),
        _ref("2", "Vendas Brasil"),
        _ref("3", "Vendas Brasil Regional 2024"),
    ]

    result = rank_similar("vendas brasil", candidates)

    scores = [m.score for m in result]
    assert scores == sorted(scores, reverse=True)
    assert result[0].name == "Vendas Brasil"


def test_rank_similar_match_exato_score_maximo() -> None:
    candidates = [
        _ref("1", "Vendas Brasil"),
        _ref("2", "Outro Conteudo"),
    ]

    result = rank_similar("Vendas Brasil", candidates)

    assert result[0].name == "Vendas Brasil"
    assert result[0].score == 1.0
    assert all(0.0 <= m.score <= 1.0 for m in result)


def test_rank_similar_sem_candidatos_retorna_lista_vazia() -> None:
    assert rank_similar("qualquer termo", []) == []


def test_rank_similar_respeita_limit() -> None:
    candidates = [_ref(str(i), f"Vendas {i}") for i in range(10)]

    result = rank_similar("vendas", candidates, limit=3)

    assert len(result) == 3


def test_rank_similar_case_insensitive_e_acentos() -> None:
    candidates = [_ref("1", "Vendas Brasília")]

    # Termo sem acento e em maiúsculas deve casar exatamente após normalização.
    result = rank_similar("VENDAS BRASILIA", candidates)

    assert len(result) == 1
    assert result[0].score == 1.0

"""Camada de validação pura do MCP Tableau.

Funções puras que não conhecem rede nem o Tableau Server Client (TSC) e dependem
apenas dos modelos da Tarefa 1.0. São testáveis sem mocks de rede.

Exposições principais:
- `inspect_structure` / `StructureParseError` — parsing estrutural do workbook.
- `audit_complexity` — auditoria de complexidade contra limiares.
- `detect_blank_render` / `BlankRenderError` — heurística de tela em branco.
- `rank_similar` — ranking fuzzy de similaridade.
- `check_source_file` / `check_inline_rows` / `check_extracted_rows` — salvaguardas
  puras de volume das operações Hyper.
"""

from mcp_tableau.validation.complexity import audit_complexity
from mcp_tableau.validation.similarity import rank_similar
from mcp_tableau.validation.structure import StructureParseError, inspect_structure
from mcp_tableau.validation.visual import BlankRenderError, detect_blank_render
from mcp_tableau.validation.volume import (
    check_extracted_rows,
    check_inline_rows,
    check_source_file,
)

__all__ = [
    "BlankRenderError",
    "StructureParseError",
    "audit_complexity",
    "check_extracted_rows",
    "check_inline_rows",
    "check_source_file",
    "detect_blank_render",
    "inspect_structure",
    "rank_similar",
]

# Tarefa 5.0: Integração MCP, verificação RF11 e cobertura

## Visão geral

Fechar a feature validando o contrato ponta a ponta e a qualidade. Testes de integração do protocolo MCP in-memory (sobe o FastMCP em processo, com cliente mockado) verificam a **serialização** do novo contrato (`worksheets[].id`, `worksheets[].name`, `filters[].worksheet_id`), inclusive o caminho degradado (`id: null` presente, não omitido) e o encadeamento com a ferramenta de render. Verificar a consistência de `id` em similaridade/linhagem (RF11). Adicionar smoke de integração real marcado (`@pytest.mark.integration`) e garantir cobertura ≥80%.

<skills>
### Conformidade com skills

- **testing-standards**: integração MCP in-memory na suite rápida; integração com Tableau real marcada e fora da suite padrão; meta de cobertura ≥80% (`--cov=mcp_tableau --cov-fail-under=80`).
- **code-standards**: contrato exposto via Pydantic; sem credenciais em logs/erros.
</skills>

<requirements>
- RF3: id serializado é aceito pela ferramenta de render sem transformação.
- RF4/RF7/RF10: `id`/`worksheet_id` `null` no caminho degradado, com `status="success"`.
- RF8: contrato `{id, name, ...}` serializado corretamente.
- RF9: contrato documentado e verificável pelo cliente MCP.
- RF11: similaridade e linhagem verificadas quanto à consistência do formato de `id`.
</requirements>

## Subtarefas

- [ ] 5.1 Testes MCP in-memory de serialização do novo contrato (sucesso e degradado).
- [ ] 5.2 Teste de encadeamento: `id` da inspeção aceito por `render_view_image` (ambas mockadas no limite do cliente).
- [ ] 5.3 Verificação RF11: confirmar que `SimilarityMatch`/`LineageNode`/`ContentRef` expõem `id` consistente; alinhar divergências se houver.
- [ ] 5.4 Smoke de integração real marcado (`@pytest.mark.integration`): worksheets visíveis com `id` não nulo; sheets ocultas `null`.
- [ ] 5.5 Rodar a suite com cobertura e garantir ≥80% (`--cov=mcp_tableau --cov-fail-under=80`).

## Detalhes de implementação

Ver `techspec.md` → "Abordagem de testes" (Integração e E2E), "Endpoints da API" (cenários sucesso/degradado) e "Arquivos relevantes e dependentes" (verificação RF11 em `tableau/metadata.py`). Sem Playwright/E2E gráfico (servidor MCP headless).

## Critérios de sucesso

- Contrato serializado expõe `worksheets[].id/name`, `dashboards[].id/name` e `filters[].worksheet_id` corretamente tipados.
- Caminho degradado serializa `id: null` (campo presente), com `status="success"`.
- `id` da inspeção é aceito pela ferramenta de render sem transformação.
- Similaridade/linhagem confirmadas consistentes (RF11).
- Suite rápida verde (`uv run pytest`); cobertura ≥80%.

## Testes da tarefa

### Testes unitários

- [ ] (RF11) Verificação de consistência de `id` em `SimilarityMatch`/`LineageNode`/`ContentRef` (assert de presença/tipo de `id`).

### Testes de integração

**`tests/test_mcp_integration.py`** (FastMCP in-memory, cliente mockado)
- [ ] `test_inspect_workbook_structure_contrato_serializa_sheetref` — JSON com `worksheets[].id`, `worksheets[].name`, `filters[].worksheet_id` presentes e tipados.
- [ ] `test_inspect_workbook_structure_degradado_serializa_id_null` — caminho degradado serializa `id: null` (sem omitir o campo).
- [ ] `test_render_aceita_id_do_structure_report` — encadeamento: id da inspeção aceito pela tool de render.

**`tests/integration/` (`@pytest.mark.integration`, sob demanda)**
- [ ] `test_real_inspect_structure_retorna_luids_validos` — sandbox: worksheets visíveis com `id` não nulo e renderizável; sheets ocultas `null`.

### Testes E2E (se aplicável)

- N/A (servidor MCP headless; smoke real acima cobre o fluxo ponta a ponta sob demanda).

## Arquivos relevantes

- `tests/test_mcp_integration.py` — ampliado.
- `tests/integration/test_tableau_real.py` — ampliado (smoke marcado).
- `src/mcp_tableau/tableau/metadata.py` — referência para verificação RF11.
- `tests/test_models.py`, `tests/validation/*`, `tests/tableau/test_client.py`, `tests/tools/test_qa.py` — entram na medição de cobertura.

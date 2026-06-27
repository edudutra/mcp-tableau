# Tarefa 2.0: Camada de validação pura — `structure.py` e `complexity.py`

## Visão geral

Adaptar a camada de validação pura ao novo contrato sem introduzir rede. `inspect_structure` passa a construir `SheetRef(name=..., id=None)` para worksheets/dashboards e `FilterInfo(worksheet_id=None, ...)` — os LUIDs são preenchidos depois, na ferramenta (Tarefa 4.0). `complexity.py` (`_measure`) é confirmado/ajustado para operar sobre `list[SheetRef]` mantendo as contagens corretas.

<skills>
### Conformidade com skills

- **code-standards**: regras de validação ficam em `validation/`, puras e testáveis sem rede; type hints completos.
- **testing-standards**: funções puras testadas com mesma entrada → mesmo resultado; cobrir casos válidos, inválidos e de borda; sem rede/relógio.
</skills>

<requirements>
- RF1/RF2: worksheets/dashboards emitidos como `SheetRef`.
- RF4/RF7: `id`/`worksheet_id` nulos na camada pura (sem LUID local).
- Manter pureza de `validation/structure.py` (sem TSC/rede).
- Não alterar o comportamento de auditoria de complexidade (não-regressão).
</requirements>

## Subtarefas

- [ ] 2.1 Em `structure.py`, montar `SheetRef(name=ws, id=None)` para worksheets e dashboards.
- [ ] 2.2 Em `structure.py`, montar `FilterInfo(..., worksheet_id=None)` (LUID preenchido na Tarefa 4.0).
- [ ] 2.3 Garantir que `inspect_structure` permanece puro (sem chamadas de rede/cliente).
- [ ] 2.4 Em `complexity.py`, confirmar/ajustar `_measure` (`len(report.worksheets)`/`len(report.dashboards)`) sobre `list[SheetRef]`.
- [ ] 2.5 Atualizar fixtures dos testes de `structure` e `complexity` de `list[str]` para `list[SheetRef]` e adicionar os novos casos.

## Detalhes de implementação

Ver `techspec.md` → "Visão dos componentes" (itens `validation/structure.py` e `validation/complexity.py`) e "Mapeamento REST → contrato" (a coluna de origem só é aplicada na Tarefa 4.0). Aqui os ids nascem `None`.

## Critérios de sucesso

- `inspect_structure` retorna worksheets/dashboards como `SheetRef` com `id is None` e `name` correto.
- `FilterInfo.worksheet_id is None` na saída do parsing puro.
- Nenhuma chamada de rede/cliente ocorre no parsing.
- `complexity` produz as mesmas métricas/findings de antes para estruturas equivalentes.
- Casos existentes (filtro sem lógica, conexão inválida, campo quebrado) continuam detectados.

## Testes da tarefa

### Testes unitários

**`tests/validation/test_structure.py`**
- [ ] `test_inspect_structure_worksheets_viram_sheetref_id_none` — worksheets têm `id is None` e `name` correto.
- [ ] `test_inspect_structure_dashboards_viram_sheetref_id_none` — idem para dashboards.
- [ ] `test_inspect_structure_filtros_worksheet_id_none` — `FilterInfo.worksheet_id is None` no parsing puro.
- [ ] `test_inspect_structure_permanece_puro_sem_rede` — nenhuma chamada de cliente/rede ocorre.
- [ ] Regressão dos casos existentes (filtro sem lógica, conexão inválida, campo quebrado) sob o novo tipo.

**`tests/validation/test_complexity.py`** (helper `_report` gerando `SheetRef`)
- [ ] `test_measure_conta_worksheets_sobre_sheetref` — `metrics.worksheets == len(list[SheetRef])`.
- [ ] `test_measure_conta_dashboards_sobre_sheetref` — idem dashboards.
- [ ] `test_complexity_excede_worksheets_com_sheetref` — limiar excedido conta corretamente objetos.
- [ ] Parametrizações existentes mantidas, agora com `SheetRef`.

### Testes de integração

- N/A.

## Arquivos relevantes

- `src/mcp_tableau/validation/structure.py` — modificado.
- `src/mcp_tableau/validation/complexity.py` — verificado/ajustado.
- `tests/validation/test_structure.py`, `tests/validation/test_complexity.py` — ampliados.

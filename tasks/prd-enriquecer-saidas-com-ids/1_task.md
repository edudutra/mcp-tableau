# Tarefa 1.0: Modelos de dados — `SheetRef`, `StructureReport` e `FilterInfo`

## Visão geral

Introduzir o novo contrato de saída para objetos identificáveis da inspeção estrutural. Criar o modelo Pydantic `SheetRef{id, name}` e alterar `StructureReport` (worksheets/dashboards passam de `list[str]` para `list[SheetRef]`) e `FilterInfo` (ganha `worksheet_id`). `ConnectionInfo` permanece inalterada (RF5 fora deste ciclo). É a base de tipos para todas as demais tarefas e concentra a quebra de contrato.

<skills>
### Conformidade com skills

- **code-standards**: modelos sempre via Pydantic em `models.py`; type hints modernos (`str | None`); sem dicts soltos como contrato.
- **testing-standards**: todo modelo novo/alterado coberto por teste unitário; nomes `test_<unidade>_<cenario>_<resultado>`.
</skills>

<requirements>
- RF1: worksheet retornado como objeto com `id` e `name`.
- RF2: dashboard retornado como objeto com `id` e `name`.
- RF4: `id` ausente é representado como `null` (não omitido), preservando `name`.
- RF6: `FilterInfo` passa a referenciar o `worksheet_id`.
- RF7: `worksheet_id` indisponível é `null` (não omitido).
- RF8: objetos identificáveis representados como `{id, name, ...}` em vez de string.
- Contrato incompatível assumido (sem camada de compatibilidade).
</requirements>

## Subtarefas

- [ ] 1.1 Criar `SheetRef(BaseModel)` com `id: str | None = None` e `name: str` em `models.py`.
- [ ] 1.2 Alterar `StructureReport.worksheets` e `.dashboards` para `list[SheetRef]`.
- [ ] 1.3 Adicionar `worksheet_id: str | None = None` a `FilterInfo`.
- [ ] 1.4 Confirmar que `ConnectionInfo` permanece sem `id` (não-regressão de contrato).
- [ ] 1.5 Escrever os testes unitários de `models.py`.

## Detalhes de implementação

Ver `techspec.md` → seção "Modelos de dados" (`SheetRef`, `StructureReport`, `FilterInfo`, `ConnectionInfo`). Não reimplementar regras aqui; seguir tabelas de campos e exemplos JSON da techspec.

## Critérios de sucesso

- `SheetRef` aceita `id=None` e serializa `id: null` (campo presente, não omitido).
- `StructureReport` aceita `list[SheetRef]` em worksheets/dashboards e **rejeita** `list[str]`.
- `FilterInfo` expõe `worksheet_id` com default `None`.
- `ConnectionInfo` inalterada.
- `ruff check`/`ruff format` sem erros; type hints completos.

## Testes da tarefa

### Testes unitários

- [ ] `test_sheetref_aceita_id_none_preserva_name` — `SheetRef(id=None, name="X")` válido e serializa `id: null`.
- [ ] `test_sheetref_serializa_id_luid` — `SheetRef(id="luid", name="X")` serializa ambos.
- [ ] `test_structure_report_worksheets_aceita_list_sheetref` — atribuir `list[SheetRef]` a `worksheets`/`dashboards`.
- [ ] `test_structure_report_rejeita_list_str_em_worksheets` — passar `["A"]` levanta `ValidationError` (contrato incompatível confirmado).
- [ ] `test_filter_info_worksheet_id_default_none` — `FilterInfo` sem `worksheet_id` assume `None`.
- [ ] `test_filter_info_aceita_worksheet_id` — `worksheet_id="luid"` preservado.
- [ ] `test_connection_info_inalterada` — `ConnectionInfo` continua sem `id`.

### Testes de integração

- N/A (serialização end-to-end coberta na Tarefa 5.0).

## Arquivos relevantes

- `src/mcp_tableau/models.py` — modificado.
- `tests/test_models.py` — ampliado.

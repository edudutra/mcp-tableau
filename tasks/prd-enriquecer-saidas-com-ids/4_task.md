# Tarefa 4.0: Orquestração na ferramenta QA — enriquecimento best-effort e contrato

## Visão geral

Conectar as peças na ferramenta `inspect_workbook_structure` (`tools/qa.py`): após download + parsing puro, invocar `list_workbook_view_luids` (Tarefa 3.0) e aplicar o **merge por nome**, preenchendo `SheetRef.id` (worksheets/dashboards) e `FilterInfo.worksheet_id`. O enriquecimento é **best-effort**: qualquer `TableauClientError` ao obter as views degrada para `id=null` e o relatório retorna com `status="success"` (RF10). Atualizar a docstring/contrato da ferramenta para o novo formato (RF9).

<skills>
### Conformidade com skills

- **code-standards**: ferramenta fina que orquestra e delega; docstring é o contrato exposto ao agente; entrada/saída Pydantic; sem segredos em logs.
- **testing-standards**: mockar `tableau_session`, `load_settings`, `inspect_structure` e o novo método do cliente; cobrir caminho feliz, degradação e propagação de erro.
</skills>

<requirements>
- RF1/RF2/RF3: worksheets/dashboards com `id` renderizável (LUID casado por nome).
- RF4/RF7: sem correspondência ⇒ `id`/`worksheet_id` permanecem `null`.
- RF6: `FilterInfo.worksheet_id` preenchido por correspondência de nome.
- RF9: docstring/contrato da ferramenta atualizados.
- RF10: degradação não introduz novos erros nem falha a ferramenta.
- Observabilidade: log WARNING ao degradar (com `workbook_id` e `ErrorCode`, sem credenciais); log DEBUG da contagem de sheets sem LUID.
</requirements>

## Subtarefas

- [ ] 4.1 Implementar `_enrich_with_view_luids(client, report, workbook_id)` que casa nome → LUID e preenche `SheetRef.id`/`FilterInfo.worksheet_id`.
- [ ] 4.2 Integrar o enriquecimento ao fluxo de `inspect_workbook_structure`, após o parsing, dentro da sessão autenticada.
- [ ] 4.3 Tratar falha de `list_workbook_view_luids` como degradação (captura de `TableauClientError`), mantendo `status="success"` e ids `null`.
- [ ] 4.4 Garantir que erro de download (`NOT_FOUND`/`UPSTREAM_ERROR`) continua sendo propagado como `ToolError` antes do enriquecimento.
- [ ] 4.5 Adicionar logs (WARNING na degradação; DEBUG na contagem de nulos) sem vazar credenciais.
- [ ] 4.6 Atualizar a docstring/contrato da ferramenta (RF9).
- [ ] 4.7 Escrever os testes unitários da ferramenta.

## Detalhes de implementação

Ver `techspec.md` → "Principais interfaces" (`_enrich_with_view_luids`), "Mapeamento REST → contrato", "Endpoints da API" (cenários sucesso/degradado/erro) e "Monitoramento e observabilidade". Reutilizar `audit_workbook_complexity` sem alterações de comportamento.

## Critérios de sucesso

- Worksheets/dashboards cujo nome casa com o mapa recebem o LUID; demais permanecem `id=null`.
- Filtros recebem `worksheet_id` por correspondência de nome.
- Falha ao obter views ⇒ `StructureReport` com ids `null` e `status="success"` (nunca `ToolError`).
- Download inexistente ⇒ `ToolError(NOT_FOUND)` e enriquecimento não é chamado.
- `SheetRef.id` retornado é aceito sem transformação por `render_view_image` (encadeamento).
- Docstring reflete o novo contrato.

## Testes da tarefa

### Testes unitários

**`tests/tools/test_qa.py`** (`tableau_session`, `load_settings`, `inspect_structure` e novo método mockados)
- [ ] `test_inspect_structure_enriquece_ids_por_nome` — sheets cujo nome casa recebem LUID; filtros recebem `worksheet_id`.
- [ ] `test_inspect_structure_sheet_sem_correspondencia_id_none` — worksheet sem view publicada mantém `id=None`.
- [ ] `test_inspect_structure_filtro_worksheet_id_preenchido` — `FilterInfo.worksheet_id` casado por nome.
- [ ] `test_inspect_structure_degrada_quando_populate_views_falha` — `TableauClientError(UPSTREAM_ERROR)` ⇒ ids `null` e `status="success"`.
- [ ] `test_inspect_structure_degrada_quando_metadata_indisponivel` — erro de endpoint indisponível ⇒ degrada, não falha.
- [ ] `test_inspect_structure_not_found_antes_do_enriquecimento` — download `NOT_FOUND` ⇒ `ToolError`; enriquecimento nunca chamado.
- [ ] `test_inspect_structure_id_aceito_por_render` — `SheetRef.id` é exatamente o formato passado a `render_view_image` (contrato de encadeamento).
- [ ] `test_audit_complexity_inalterado_com_sheetref` — auditoria correta com o novo tipo (não-regressão).

### Testes de integração

- Cobertos na Tarefa 5.0 (MCP in-memory + serialização do contrato).

## Arquivos relevantes

- `src/mcp_tableau/tools/qa.py` — modificado.
- `tests/tools/test_qa.py` — ampliado.
- `src/mcp_tableau/tableau/client.py`, `src/mcp_tableau/validation/structure.py`, `src/mcp_tableau/models.py` — dependências (Tarefas 1.0–3.0).

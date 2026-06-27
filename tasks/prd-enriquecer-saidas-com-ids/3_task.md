# Tarefa 3.0: Cliente REST — `list_workbook_view_luids`

## Visão geral

Adicionar à camada de integração (`tableau/client.py`) um novo método `list_workbook_view_luids(workbook_id) -> dict[str, str]` que executa `workbooks.populate_views` e devolve o mapa `nome_da_view → LUID` das views publicadas. Views sem LUID (sheets ocultas) são omitidas do mapa. Reutiliza `_with_reauth` (retry único em 401) e a tradução de erros existente (`_translate`), sem vazar credenciais. Independente do contrato `SheetRef` — pode ser desenvolvido em paralelo à Tarefa 1.0.

<skills>
### Conformidade com skills

- **code-standards**: todo acesso ao Tableau via `tableau/client.py`; usar `tableauserverclient`; tratar paginação/limites; capturar exceções específicas do TSC; nunca logar segredos.
- **testing-standards**: mockar o TSC/cliente; nunca acessar servidor real em unitário; asserts específicos de chamada.
</skills>

<requirements>
- RF3: o LUID retornado deve ser o identificador aceito pelas ferramentas de render (`views.get_by_id`).
- RF4: views sem LUID são omitidas (a tool então mantém `id=null`).
- Segurança: mensagens de erro sem PAT/token.
- Desempenho: chamada única (`usage=False`), sem laço por sheet.
</requirements>

## Subtarefas

- [ ] 3.1 Implementar `list_workbook_view_luids` usando `populate_views` e montar o mapa `nome → LUID`.
- [ ] 3.2 Omitir do mapa views com LUID vazio/`None`; definir regra determinística para nomes duplicados (última ocorrência vence).
- [ ] 3.3 Envolver a operação em `_with_reauth`; garantir tradução de erros via `_translate` (mesmos `ErrorCode`).
- [ ] 3.4 Escrever os testes unitários do cliente com TSC mockado.

## Detalhes de implementação

Ver `techspec.md` → "Principais interfaces" (assinatura), "Parâmetros fixados no upstream" (`usage=False`, `_with_reauth`) e "Pontos de integração". Não reimplementar autenticação/retry — reutilizar o existente.

## Critérios de sucesso

- Método retorna `dict[str, str]` com nomes de view → LUID das views publicadas.
- Views sem LUID não aparecem no mapa.
- 401 dispara re-autenticação e repete a operação exatamente uma vez.
- Erros REST traduzidos para `TableauClientError` com `ErrorCode` correto, sem credenciais na mensagem.

## Testes da tarefa

### Testes unitários

**`tests/tableau/test_client.py`** (TSC mockado)
- [ ] `test_list_workbook_view_luids_retorna_mapa_nome_luid` — `populate_views` mockado retorna views; método devolve `{name: id}`.
- [ ] `test_list_workbook_view_luids_omite_view_sem_luid` — `ViewItem` com `id` vazio/`None` é omitido do mapa.
- [ ] `test_list_workbook_view_luids_nomes_duplicados_ultima_vence` — comportamento determinístico para nomes repetidos.
- [ ] `test_list_workbook_view_luids_reautentica_em_401` — 401 dispara re-auth e repete uma vez (via `_with_reauth`).
- [ ] `test_list_workbook_view_luids_traduz_404_not_found` — erro REST 404 → `TableauClientError(NOT_FOUND)`.
- [ ] `test_list_workbook_view_luids_nao_vaza_credenciais` — mensagem de erro sem PAT/token.

### Testes de integração

- Smoke real coberto na Tarefa 5.0 (`@pytest.mark.integration`).

## Arquivos relevantes

- `src/mcp_tableau/tableau/client.py` — modificado.
- `tests/tableau/test_client.py` — ampliado.

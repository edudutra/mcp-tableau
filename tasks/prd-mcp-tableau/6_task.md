# Tarefa 6.0: Tools — Capacidade 4 Metadados (`tools/metadata.py`)

## Visão geral

Implementa as ferramentas MCP da Capacidade 4 (Dicionário/Contexto), que orquestram o
`MetadataClient` (Tarefa 3.0) e a validação de similaridade pura (Tarefa 4.0): linhagem
descendente (`get_downstream_lineage`), linhagem ascendente (`get_upstream_lineage`), dicionário
de fonte de dados (`get_datasource_dictionary`) e busca fuzzy de conteúdo semelhante
(`search_similar_content`). Habilita a etapa "Descobrir" da jornada do agente, retornando
resultados estruturados e atribuíveis ou `ToolError`.

<skills>
### Conformidade com skills

- **`code-standards`** — ferramentas finas com docstring-contrato, acesso a metadados só via
  camada `tableau/`, erros acionáveis, type hints.
- **`testing-standards`** — metadata client mockado; nomenclatura padrão.
</skills>

<requirements>
- **RF17**: Linhagem descendente de uma fonte de dados.
- **RF18**: Linhagem ascendente de um conteúdo.
- **RF19**: Dicionário de fonte de dados (nomes, fórmulas, descrições homologadas).
- **RF20**: Busca de conteúdo semelhante para evitar duplicação.
- **RF21**: Resultados estruturados e atribuíveis (identificadores, nomes, projeto de origem).
- **RF22/RF23**: Status explícito e erro acionável tipado.
</requirements>

## Subtarefas

- [ ] 6.1 `get_downstream_lineage(datasource_id)` → `LineageResult` (`direction="downstream"`);
  lista vazia com `status="success"` quando não há dependentes (sobrescrita segura).
- [ ] 6.2 `get_upstream_lineage(content_id, content_type="workbook")` → `LineageResult`
  (`direction="upstream"`).
- [ ] 6.3 `get_datasource_dictionary(datasource_id)` → `DataDictionary`; `formula`/`description`
  podem ser `null`.
- [ ] 6.4 `search_similar_content(query, content_type="all", limit=10)`: listar candidatos via
  REST, ranquear com `rank_similar` (Tarefa 4.0) e retornar `SimilarityResult`; validar `limit`
  (1–50) → `VALIDATION_ERROR`; `matches: []` não é erro.
- [ ] 6.5 Mapear falhas Metadata/REST para `NOT_FOUND`/`UPSTREAM_ERROR`; registrar as tools no
  `server.py`.

## Detalhes de implementação

Ver techspec.md § "Endpoints da API" → `get_downstream_lineage`, `get_upstream_lineage`,
`get_datasource_dictionary`, `search_similar_content`; § "Modelos de dados" → `LineageResult`,
`DataDictionary`, `SimilarityResult`; e o mapeamento Tableau→contrato.

## Critérios de sucesso

- Linhagem descendente/ascendente retorna dependências atribuíveis (id, nome, tipo, projeto).
- Sem dependentes → `dependencies: []` com `status="success"`.
- Dicionário inclui fórmula de calculados e normaliza campos sem descrição para `null`.
- Busca retorna matches ordenados por `score`; sem match → lista vazia com sucesso.
- `limit` inválido retorna `VALIDATION_ERROR`.

## Testes da tarefa

### Testes unitários

- [ ] `test_get_downstream_lineage_retorna_dependencias_atribuiveis`
- [ ] `test_get_downstream_lineage_sem_dependentes_retorna_lista_vazia_sucesso`
- [ ] `test_get_upstream_lineage_workbook_retorna_fontes`
- [ ] `test_get_datasource_dictionary_inclui_formula_de_calculados`
- [ ] `test_get_datasource_dictionary_campos_sem_descricao_normalizados_null`
- [ ] `test_search_similar_content_retorna_matches_ordenados`
- [ ] `test_search_similar_content_sem_match_retorna_lista_vazia`
- [ ] `test_search_similar_content_limit_invalido_retorna_validation_error`

### Testes de integração

- [ ] (Tarefa 9.0) Cobertura via suite MCP in-memory (contrato/serialização das tools de
  metadados, client mockado).

## Arquivos relevantes

- `src/mcp_tableau/tools/metadata.py`
- `src/mcp_tableau/server.py` (registro das tools)
- `tests/tools/test_metadata.py`

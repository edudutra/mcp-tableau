# Tarefa 3.0: Camada de integração GraphQL (`tableau/metadata.py`)

## Visão geral

Implementa o `MetadataClient`, responsável por executar queries GraphQL na Tableau Metadata API
reaproveitando a sessão autenticada do `TableauClient` (Tarefa 2.0). Cobre linhagem descendente
(conteúdos que dependem de uma fonte de dados), linhagem ascendente (fontes/tabelas das quais um
conteúdo depende) e o dicionário de campos de uma fonte de dados (nome, fórmula, descrição).
Erros GraphQL e endpoints indisponíveis são mapeados para `UPSTREAM_ERROR`; campos ausentes no
upstream são normalizados para `null`.

<skills>
### Conformidade com skills

- **`code-standards`** — acesso ao Tableau só via camada `tableau/`, credenciais por env, sem
  segredos em erros, type hints, erros acionáveis.
- **`testing-standards`** — Metadata client mockado nos unitários; nomenclatura padrão.
</skills>

<requirements>
- **RF17**: Rastrear quais workbooks/conteúdos dependem de uma fonte de dados (linhagem
  descendente).
- **RF18**: Rastrear de quais fontes/tabelas um conteúdo depende (linhagem ascendente).
- **RF19**: Consultar o dicionário de uma fonte de dados (campos, fórmulas de calculados,
  descrições homologadas), quando disponíveis.
- **RF23**: Erros traduzidos de forma acionável sem expor credenciais.
- **RF24**: Degradar campos indisponíveis (Cloud vs Server) para `null`.
</requirements>

## Subtarefas

- [x] 3.1 Implementar `downstream_of_datasource(datasource_luid)` — query GraphQL
  `downstreamWorkbooks` e parsing para estrutura atribuível.
- [x] 3.2 Implementar `upstream_of_workbook(workbook_luid)` — query GraphQL
  `upstreamDatasources` (suportando workbook/datasource).
- [x] 3.3 Implementar `datasource_dictionary(datasource_luid)` — query
  `fields { name formula description }`, normalizando ausentes para `null`.
- [x] 3.4 Reaproveitar a sessão/credencial do `TableauClient` (POST GraphQL único, sem paginação
  manual no MVP) e mapear erro GraphQL/`EndpointUnavailableError` para `UPSTREAM_ERROR`.

## Detalhes de implementação

Ver techspec.md § "Principais interfaces" (assinaturas de `MetadataClient`),
§ "Pontos de integração" (Metadata API, mesma sessão da REST),
§ "Parâmetros fixados no upstream" (GraphQL POST único) e o mapeamento Tableau→contrato.
A montagem dos modelos `LineageResult`/`DataDictionary` finais ocorre nas tools (Tarefa 6.0);
aqui as funções retornam os dados parseados.

## Critérios de sucesso

- Query GraphQL é montada corretamente e a resposta é parseada para a estrutura esperada.
- Linhagem ascendente e descendente retornam nós atribuíveis (id, nome, tipo, projeto).
- Dicionário inclui fórmula de campos calculados e normaliza descrições ausentes para `null`.
- Erro GraphQL/endpoint indisponível vira `UPSTREAM_ERROR` acionável, sem vazar credenciais.

## Testes da tarefa

### Testes unitários

- [x] `test_metadata_query_monta_graphql_e_parseia_resposta`
- [x] `test_metadata_erro_graphql_vira_upstream_error`

### Testes de integração

- [ ] (Tarefa 9.0) `test_integration_metadata_lineage_responde`
  (`@pytest.mark.integration`, sandbox real).

## Arquivos relevantes

- `src/mcp_tableau/tableau/metadata.py`
- `tests/tableau/test_metadata.py`

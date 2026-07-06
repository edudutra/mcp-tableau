# Tarefa 7.0: Publicação `.hyper` e registro no servidor

## Visão geral

Fechar a integração da feature no servidor MCP: estender `publish_datasource` (`tools/deploy.py`) para aceitar `.hyper` no conjunto de extensões válidas (mudança de uma linha + docstring), registrar `hyper.register(mcp)` em `server.py::register_tools()` e cobrir a superfície completa com testes de integração MCP in-memory (17 tools: 10 existentes + 7 novas), incluindo serialização dos novos contratos via transporte MCP.

<skills>
### Conformidade com skills

- `code-standards` — reutilização integral do fluxo `_publish()` existente (zero duplicação), registro via `register(mcp)` sem acoplar ao singleton (memória `tool-registration-seam`), docstring atualizada com requisito de versão do Tableau Server.
- `testing-standards` — integração MCP in-memory na suite rápida (FastMCP client em memória), validação de schemas de entrada das tools.
</skills>

<requirements>
- RF21 — publicar `.hyper` como datasource no Tableau Server/Cloud, integrado ao fluxo existente (mesmos parâmetros de projeto de destino e política de sobrescrita).
- RF22 — retorno da publicação inclui identificadores do datasource criado/atualizado (`content_id`), permitindo encadeamento com as tools de metadados e QA existentes.
</requirements>

## Subtarefas

- [x] 7.1 Estender `publish_datasource` em `tools/deploy.py`: conjunto de extensões válidas de `{".tds", ".tdsx"}` para `{".tds", ".tdsx", ".hyper"}`; nenhum outro comportamento muda (política `OVERWRITE_NOT_ALLOWED`, retorno `PublishResult`, tradução de erros intactos).
- [x] 7.2 Atualizar a docstring de `publish_datasource` citando o requisito Tableau Server ≥ 2021.4 para `.hyper` multi-tabela (2021.3↓ exige tabela única `Extract.Extract`).
- [x] 7.3 Incluir `hyper.register(mcp)` em `server.py::register_tools()`.
- [x] 7.4 Estender `tests/tools/test_deploy.py` com os casos `.hyper` (79–81).
- [x] 7.5 Estender `tests/test_mcp_integration.py` com os casos 82–86 (contagem de tools, schemas de entrada, serialização de `HyperCreateResult`, `ToolError` e `VolumeAlert` via transporte MCP).

## Detalhes de implementação

Ver techspec.md, seções "`publish_datasource` *(modificação — RF21–RF22)*" em "Endpoints da API", decisão 3 ("estender em vez de criar tool nova") em "Principais decisões" e o risco "Compatibilidade de `.hyper` multi-tabela na publicação" em "Riscos conhecidos".

## Critérios de sucesso

- `publish_datasource` aceita `.hyper` mantendo intactos parâmetros, política de sobrescrita e retorno com `content_id`.
- Servidor expõe exatamente 17 tools, todas com schemas de entrada válidos.
- Os três discriminadores (`success`, `error`, `volume_alert`) sobrevivem à serialização via transporte MCP.
- Suite rápida verde; cobertura ≥ 80%; `ruff` limpo.

## Testes da tarefa

### Testes unitários

`tests/tools/test_deploy.py` (casos 79–81 da techspec):

- [x] 79. `test_publish_datasource_aceita_extensao_hyper`
- [x] 80. `test_publish_datasource_hyper_respeita_politica_de_sobrescrita`
- [x] 81. `test_publish_datasource_hyper_retorna_content_id_para_encadeamento`

### Testes de integração

`tests/test_mcp_integration.py` (casos 82–86, FastMCP in-memory, suite rápida):

- [x] 82. `test_servidor_expoe_dezessete_tools`
- [x] 83. `test_tools_hyper_declaram_schemas_de_entrada_validos`
- [x] 84. `test_chamada_create_hyper_from_inline_via_cliente_mcp_serializa_resultado`
- [x] 85. `test_chamada_query_hyper_com_arquivo_inexistente_serializa_tool_error`
- [x] 86. `test_volume_alert_serializado_via_transporte_mcp_mantem_status_volume_alert`

### Testes E2E (se aplicável)

- Publicação real no Tableau coberta na tarefa 8.0 (caso 92, `@pytest.mark.integration` com credenciais).

## Arquivos relevantes

- `src/mcp_tableau/tools/deploy.py` — modificado (extensão `.hyper` + docstring)
- `src/mcp_tableau/server.py` — modificado (`hyper.register(mcp)`)
- `tests/tools/test_deploy.py` — modificado
- `tests/test_mcp_integration.py` — modificado
- `src/mcp_tableau/tools/hyper.py` — dependência (as 7 tools prontas, tarefas 3.0–6.0)

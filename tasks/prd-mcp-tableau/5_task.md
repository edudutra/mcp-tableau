# Tarefa 5.0: Tools — Capacidade 1 Deploy (`tools/deploy.py`)

## Visão geral

Implementa as ferramentas MCP de publicação/sobrescrita (Capacidade 1), registradas no
`server.py`. São ferramentas finas que validam entrada localmente e delegam ao `TableauClient`
(Tarefa 2.0): `publish_workbook` (`.twb`/`.twbx`) e `publish_datasource` (`.tds`/`.tdsx`). Ambas
resolvem o projeto por nome, respeitam a indicação explícita de overwrite, suportam chunking
transparente para artefatos grandes e retornam `PublishResult` ou o envelope `ToolError`.

<skills>
### Conformidade com skills

- **`code-standards`** — ferramentas FastMCP finas com docstring-contrato, validação local antes
  de rede, acesso ao Tableau só via `TableauClient`, erros acionáveis sem segredos.
- **`testing-standards`** — cliente Tableau mockado; nomenclatura padrão; cobertura das tools.
</skills>

<requirements>
- **RF1/RF2**: Publicar novo workbook / nova fonte de dados em projeto especificado.
- **RF3/RF4**: Sobrescrever workbook/datasource existente gerando nova versão mediante overwrite
  explícito.
- **RF5**: Suportar artefatos acima do limite de envio único (chunking transparente).
- **RF6**: Retornar identificador, projeto de destino e status.
- **RF7**: Recusar sobrescrita sem indicação explícita, retornando `OVERWRITE_NOT_ALLOWED`.
- **RF22/RF23**: Saída estruturada com status e erro acionável tipado.
</requirements>

## Subtarefas

- [ ] 5.1 Implementar `publish_workbook(file_path, project_name, overwrite=false)`: validar
  extensão/existência do arquivo (`INVALID_FILE`), resolver projeto (`PROJECT_NOT_FOUND`),
  aplicar `PublishMode` e retornar `PublishResult`.
- [ ] 5.2 Implementar `publish_datasource(file_path, project_name, overwrite=false)` análoga para
  `.tds`/`.tdsx`, com `content_type="datasource"`.
- [ ] 5.3 Tratar overwrite: `overwrite=false` em conteúdo existente retorna
  `OVERWRITE_NOT_ALLOWED`; `overwrite=true` usa `PublishMode.Overwrite` e reporta
  `mode="overwrite"`; artefato grande define `chunked=true`.
- [ ] 5.4 Mapear falhas de auth/permissão/payload/upstream do `TableauClient` para `ToolError`
  sem vazar token; registrar as ferramentas no `server.py`.

## Detalhes de implementação

Ver techspec.md § "Endpoints da API" → `publish_workbook` e `publish_datasource` (parâmetros,
respostas, exemplos), § "Modelos de dados" → `PublishResult` e § "Visão dos componentes"
(`tools/deploy.py` fino, delega ao `TableauClient`).

## Critérios de sucesso

- Arquivo válido chama o client e retorna `PublishResult` com os campos obrigatórios.
- Extensão inválida ou arquivo inexistente retorna `INVALID_FILE` **sem** chamar o client.
- Projeto inexistente retorna `PROJECT_NOT_FOUND`.
- `overwrite=false` em conteúdo existente retorna `OVERWRITE_NOT_ALLOWED` (RF7).
- `overwrite=true` usa `PublishMode.Overwrite`; arquivo grande define `chunked=true`.
- Falha de auth retorna `AUTH_FAILED` sem vazar o token.

## Testes da tarefa

### Testes unitários

- [ ] `test_publish_workbook_arquivo_valido_chama_client_e_retorna_publishresult`
- [ ] `test_publish_workbook_extensao_invalida_retorna_error_invalid_file_sem_chamar_client`
- [ ] `test_publish_workbook_arquivo_inexistente_retorna_error_invalid_file`
- [ ] `test_publish_workbook_projeto_inexistente_retorna_error_project_not_found`
- [ ] `test_publish_workbook_overwrite_false_em_conteudo_existente_retorna_overwrite_not_allowed`
- [ ] `test_publish_workbook_overwrite_true_usa_publishmode_overwrite`
- [ ] `test_publish_workbook_arquivo_grande_define_chunked_true`
- [ ] `test_publish_workbook_auth_falha_retorna_error_auth_failed_sem_vazar_token`
- [ ] `test_publish_datasource_extensao_tdsx_aceita`
- [ ] `test_publish_datasource_extensao_invalida_rejeitada`

### Testes de integração

- [ ] (Tarefa 9.0) `test_mcp_publish_workbook_contrato_de_entrada_e_saida_serializa`
  (MCP in-memory, client mockado).

## Arquivos relevantes

- `src/mcp_tableau/tools/__init__.py`
- `src/mcp_tableau/tools/deploy.py`
- `src/mcp_tableau/server.py` (registro das tools)
- `tests/tools/test_deploy.py`

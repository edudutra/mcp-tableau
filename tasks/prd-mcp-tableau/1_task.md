# Tarefa 1.0: Fundação do projeto (config, models, server, dependências)

## Visão geral

Estabelece a base sobre a qual todas as demais tarefas dependem: configuração por variáveis
de ambiente (`config.py`), todos os contratos Pydantic de entrada/saída e o envelope de erro
tipado (`models.py`), o bootstrap do servidor FastMCP em transporte stdio (`server.py` +
`main.py`) e as dependências de runtime/dev declaradas no `pyproject.toml`, além do
`.env.example`. Nenhuma ferramenta é implementada aqui — apenas os contratos e a infraestrutura
de inicialização.

<skills>
### Conformidade com skills

- **`code-standards`** — estilo ruff (linha ≤88, aspas duplas, f-strings), type hints
  obrigatórios, modelos Pydantic como contrato, credenciais por env, sem segredos em logs.
- **`testing-standards`** — unitários para `config.py`/`models.py`, fixtures em `conftest.py`,
  `monkeypatch.setenv`, nomenclatura `test_<unidade>_<cenario>_<resultado>`.
</skills>

<requirements>
- **RF22**: Toda ferramenta deve retornar resultado estruturado e legível por máquina, com
  status explícito de sucesso ou falha (contratos Pydantic + envelope de erro).
- **RF23**: Em caso de falha, retornar mensagem de erro acionável que identifique a causa
  provável, sem expor credenciais (envelope `ToolError` + redação de segredos).
- Restrição técnica: autenticação via PAT lida de env; transporte stdio; Python ≥ 3.13.
</requirements>

## Subtarefas

- [ ] 1.1 Adicionar dependências de runtime ao `pyproject.toml` (`fastmcp`, `tableauserverclient`,
  `pydantic`, `python-dotenv`, `tableaudocumentapi`, `Pillow`, `rapidfuzz`) e dev
  (`pytest`, `pytest-cov`, `ruff`).
- [ ] 1.2 Implementar `config.py` com `Settings` (Pydantic `BaseSettings`): URL do servidor,
  site, PAT name/secret, timeouts e limiares de complexidade (`MAX_FILTERS`, `MAX_WORKSHEETS`,
  `MAX_DATA_SOURCES`) com defaults e override por env. Nunca logar segredos.
- [ ] 1.3 Implementar `models.py` com todos os modelos Pydantic de saída (`PublishResult`,
  `RenderImageResult`, `VisualDiagnostic`, `StructureReport`, `ComplexityReport`,
  `LineageResult`, `DataDictionary`, `SimilarityResult` e tipos aninhados) e o envelope
  `ToolError` com os códigos definidos na techspec. Campos opcionais normalizam para `null`.
- [ ] 1.4 Implementar `server.py` (instancia `FastMCP`, define transporte stdio, ponto único de
  registro das tools) e `main.py` (apenas invoca `server.run()`).
- [ ] 1.5 Criar `.env.example` com `TABLEAU_SERVER_URL`, `TABLEAU_SITE`, `TABLEAU_PAT_NAME`,
  `TABLEAU_PAT_SECRET` e limiares opcionais.
- [ ] 1.6 Criar estrutura de pacote `src/mcp_tableau/` (`__init__.py`, subpastas `tableau/`,
  `tools/`, `validation/`) e o esqueleto de `tests/` espelhando o `src`, com `conftest.py`.

## Detalhes de implementação

Ver techspec.md § "Visão dos componentes" (`server.py`, `config.py`, `models.py`),
§ "Modelos de dados" (todos os contratos JSON e o envelope `ToolError`) e
§ "Dependências técnicas". O registro efetivo das tools no `server.py` é incremental conforme
as tarefas de tools forem concluídas.

## Critérios de sucesso

- `Settings` carrega todas as variáveis obrigatórias de env e expõe limiares com default.
- Variável obrigatória ausente levanta erro claro e acionável (sem vazar valores).
- Todos os modelos da techspec serializam corretamente, com campos obrigatórios e opcionais
  (`null`) conforme contrato.
- `ToolError` serializa com `code` e `message`.
- Servidor sobe em stdio e está pronto para registrar tools; `ruff` sem violações.

## Testes da tarefa

### Testes unitários

- [ ] `test_settings_carrega_variaveis_obrigatorias`
- [ ] `test_settings_variavel_faltante_levanta_erro_claro`
- [ ] `test_settings_thresholds_default_quando_env_ausente`
- [ ] `test_settings_thresholds_override_por_env`
- [ ] `test_toolerror_serializa_com_code_e_message`
- [ ] `test_publishresult_serializa_campos_obrigatorios`
- [ ] `test_models_campos_opcionais_aceitam_null`

### Testes de integração

- [ ] (Coberto na Tarefa 9.0 — descoberta de ferramentas e serialização de contratos via MCP
  in-memory dependem das tools registradas.)

## Arquivos relevantes

- `pyproject.toml`
- `.env.example`
- `main.py`
- `src/mcp_tableau/__init__.py`
- `src/mcp_tableau/server.py`
- `src/mcp_tableau/config.py`
- `src/mcp_tableau/models.py`
- `tests/conftest.py`
- `tests/test_config.py`
- `tests/test_models.py`

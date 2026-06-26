# Relatório de Bugfix - MCP Tableau

## Resumo
- Total de Bugs: 3
- Bugs Corrigidos: 3
- Testes de Regressão Criados: 8 (1 corrigido para hermético + 7 novos)

## Detalhes por Bug

| ID | Severidade | Status | Correção | Testes Criados |
|----|------------|--------|----------|----------------|
| BUG-01 | Média | Corrigido | Teste de config tornou-se hermético via `monkeypatch.chdir(tmp_path)`, isolando a leitura de `env_file=".env"`; texto livre do `.env` comentado (fim dos `WARNING could not parse`). | `test_settings_variavel_faltante_levanta_erro_claro` (corrigido) |
| BUG-02 | Baixa | Corrigido | Nova config `TABLEAU_CA_BUNDLE` propagada ao TSC (`add_http_options({"verify": ...})`); `_translate` agora mapeia `SSLError`/`ConnectionError` para `UPSTREAM_ERROR` com mensagem acionável (TLS/CA/proxy). `.env.example` atualizado. | `test_client_traduz_sslerror_para_upstream_com_mensagem_acionavel`, `test_client_traduz_connectionerror_para_upstream_com_mensagem_acionavel`, `test_client_ca_bundle_configura_verify_no_tsc`, `test_client_sem_ca_bundle_nao_define_verify`, `test_settings_ca_bundle_default_vazio`, `test_settings_ca_bundle_override_por_env` |
| BUG-03 | Baixa | Corrigido | `TABLEAU_IT_DATASOURCE_ID` atualizado para o LUID indexado `18e985e3-…`; asserção da linhagem fortalecida (exige `status=="success"`, `direction=="downstream"`, `root` resolvido; tolera só `UPSTREAM_ERROR` para RF24, rejeita `NOT_FOUND`). | `test_integration_metadata_lineage_responde` (asserção reforçada) |

## Causa raiz e correção (detalhe)

### BUG-01 — Teste de config não hermético
- **Causa raiz:** `Settings(model_config.env_file=".env")` lê o arquivo `.env` em disco;
  o teste limpava apenas o ambiente do processo (`monkeypatch.delenv`), então um `.env`
  real repovoava as credenciais e o `ConfigError` esperado não era levantado.
- **Correção:** o teste passou a usar `monkeypatch.chdir(tmp_path)` (cwd sem `.env`),
  isolando a leitura do `env_file`. As anotações de texto livre do `.env` foram comentadas,
  eliminando os avisos `python-dotenv could not parse statement`.
- **Arquivos:** `tests/test_config.py`, `.env`.

### BUG-02 — Erro TLS mascarado + sem config de CA bundle
- **Causa raiz:** exceções de transporte do `requests` (TLS/conexão) não são
  `ServerResponseError`, caindo no fallback genérico "Falha inesperada" (viola RF23);
  e não havia como apontar um CA bundle corporativo pela aplicação.
- **Correção:** `config.py` ganhou `TABLEAU_CA_BUNDLE`; `TableauClient.__init__` injeta
  `{"verify": ca_bundle}` no TSC quando configurado; `_translate` trata `SSLError`
  (mensagem de TLS/CA) e `ConnectionError` (mensagem de conexão), ambos `UPSTREAM_ERROR`
  acionáveis. `.env.example` documenta a nova variável.
- **Arquivos:** `src/mcp_tableau/config.py`, `src/mcp_tableau/tableau/client.py`,
  `.env.example`.

### BUG-03 — Asserção fraca + IDs de sandbox desatualizados
- **Causa raiz:** o teste de linhagem aceitava `status in {"success","error"}`, passando
  mesmo com `NOT_FOUND`; e o LUID `88cd5bf4-…` não existe na Metadata API.
- **Correção:** LUID atualizado para `18e985e3-e838-469d-a103-bca7aa3dfe92` (indexado);
  asserção exige sucesso com `direction`/`root` corretos e só tolera `UPSTREAM_ERROR`
  (degradação RF24), rejeitando `NOT_FOUND`.
- **Arquivos:** `tests/integration/test_tableau_real.py`, `.env.integration`, `.env`.

## Testes
- Testes unitários: TODOS PASSANDO (132 passed, 3 deselected — `uv run pytest`)
- Testes de integração: asserção reforçada (BUG-03); coletam sem erros. Execução real
  sob demanda (`uv run pytest -m integration`) depende de Tableau/sandbox.
- Testes E2E: N/A para este escopo (sem automação E2E no projeto)
- Tipagem: SEM ERROS (`uv run ruff check` — sem mypy/pyright no projeto; type hints completos)
- Lint/format: `ruff check` e `ruff format --check` sem erros
- Cobertura: 93.76% (meta ≥ 80%); `config.py` agora em 100%

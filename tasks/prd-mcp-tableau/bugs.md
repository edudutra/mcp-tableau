# Bugs encontrados — QA MCP Tableau

Data: 2026-06-26 · Origem: execução de QA (`/executar-qa --integration`)

---

## BUG-01 — Teste de config não é hermético; falha com `.env` real presente

- **Severidade:** Média
- **Tipo:** Defeito de teste (quebra a suite rápida / portão de CI)
- **Local:** `tests/test_config.py::test_settings_variavel_faltante_levanta_erro_claro`
  + `src/mcp_tableau/config.py` (`Settings.model_config` com `env_file=".env"`)

### Descrição
O teste remove as variáveis obrigatórias via `monkeypatch.delenv` e espera que
`load_settings()` levante `ConfigError`. Porém `Settings` está configurado com
`env_file=".env"`, então o Pydantic Settings lê os valores diretamente do arquivo
`.env` em disco, repovoando as credenciais → **`DID NOT RAISE ConfigError`**.

O teste só passa quando **não** existe `.env` no repo (apenas `.env.example`). No estado
normal de trabalho de um desenvolvedor (com `.env` preenchido) a suite rápida quebra:

```
FAILED tests/test_config.py::test_settings_variavel_faltante_levanta_erro_claro
- Failed: DID NOT RAISE ConfigError
```

### Reprodução
1. Criar um `.env` válido na raiz (como o presente no projeto).
2. `uv run pytest` → 1 falha.

### Causa raiz
O teste não isola o carregamento do `env_file`. `monkeypatch.delenv` limpa o ambiente do
processo, mas não desativa a leitura do arquivo `.env`.

### Correção sugerida
No teste, neutralizar o `env_file` antes de instanciar (uma das opções):
- `monkeypatch.setattr(Settings.model_config, "env_file", None)`, ou
- `monkeypatch.chdir(tmp_path)` para um diretório sem `.env`, ou
- passar `_env_file=None` ao construir as `Settings` no `load_settings` em teste.

Há ainda ruído correlato: o `.env` atual tem texto livre (linhas 22–38, “Workbook —
MCP-Superstore…”) que o `python-dotenv` não consegue parsear, gerando vários
`WARNING ... could not parse statement`. Recomenda-se mover essas anotações para fora do
`.env` (ex.: `.env.integration` já documenta os IDs em comentários) ou comentá-las.

- **Status:** Corrigido
- **Correção aplicada:** o teste `test_settings_variavel_faltante_levanta_erro_claro`
  passou a usar `monkeypatch.chdir(tmp_path)`, isolando a leitura de `env_file=".env"`
  (cwd sem `.env`) — agora é hermético independentemente do `.env` do desenvolvedor. O
  texto livre do `.env` foi comentado, eliminando os `WARNING could not parse statement`.
- **Testes de regressão:** `tests/test_config.py::test_settings_variavel_faltante_levanta_erro_claro`
  (corrigido para ser hermético; falha se a isolação do `env_file` for revertida e houver
  um `.env` em disco).

---

## BUG-02 — Erro TLS de CA corporativa mascarado como `UPSTREAM_ERROR` genérico; sem config de CA bundle

- **Severidade:** Baixa (robustez de ambiente / observabilidade)
- **Tipo:** Tratamento de erro pouco acionável + lacuna de configuração
- **Local:** `src/mcp_tableau/tableau/client.py` (`_translate`, fallback final) e
  ausência de configuração de verificação TLS em `config.py`/`TableauClient`

### Descrição
Em rede com interceptação TLS (CA raiz autoassinada — caso da rede corporativa Dimensa),
o `tableauserverclient` (via `requests`/`certifi`) falha o handshake:

```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
  self-signed certificate in certificate chain
```

Essa exceção **não** é um `ServerResponseError`/`NotSignedInError`/`InternalServerError`,
então cai no fallback de `_translate` e o agente recebe:

```
ToolError(code=UPSTREAM_ERROR, message="Falha inesperada ao comunicar com o Tableau.")
```

A mensagem não indica que a causa é TLS/CA, violando o espírito de RF23 (erro acionável
que identifique a causa provável). Além disso, **não há como configurar o CA bundle**
pela aplicação — só funcionou exportando `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` apontando
para o store do sistema (`/etc/ssl/certs/ca-certificates.crt`).

### Reprodução
1. Sem `REQUESTS_CA_BUNDLE` apontando para a CA corporativa, rodar qualquer ferramenta
   que chame o Tableau (ex.: `render_view_image`).
2. Retorno: `UPSTREAM_ERROR` "Falha inesperada ao comunicar com o Tableau."

### Impacto
Em ambiente corporativo, a integração não conecta sem workaround manual, e o erro não
orienta o usuário/agente sobre a causa real.

### Correção sugerida
- Adicionar config opcional (ex.: `TABLEAU_CA_BUNDLE`) passada ao `requests`/sessão TSC
  (ou usar `truststore`/store do sistema por padrão).
- Em `_translate`, tratar `requests.exceptions.SSLError` (e `ConnectionError`)
  mapeando para `UPSTREAM_ERROR` com mensagem acionável (ex.: "Falha de TLS/conexão com
  o Tableau; verifique CA bundle/proxy de rede.").

- **Status:** Corrigido
- **Correção aplicada:** (1) nova config opcional `TABLEAU_CA_BUNDLE` em `config.py`,
  propagada ao TSC via `add_http_options({"verify": ca_bundle})` no `TableauClient`;
  (2) `_translate` passou a tratar `requests.exceptions.SSLError` e `ConnectionError`,
  mapeando para `UPSTREAM_ERROR` com mensagem acionável que cita TLS/CA/`TABLEAU_CA_BUNDLE`
  e proxy. `.env.example` atualizado com a nova variável.
- **Testes de regressão:**
  `tests/tableau/test_client.py::test_client_traduz_sslerror_para_upstream_com_mensagem_acionavel`,
  `::test_client_traduz_connectionerror_para_upstream_com_mensagem_acionavel`,
  `::test_client_ca_bundle_configura_verify_no_tsc`,
  `::test_client_sem_ca_bundle_nao_define_verify`,
  `tests/test_config.py::test_settings_ca_bundle_default_vazio`,
  `::test_settings_ca_bundle_override_por_env`.

---

## BUG-03 — Teste de integração de linhagem com asserção fraca + IDs de sandbox desatualizados

- **Severidade:** Baixa
- **Tipo:** Defeito de teste (asserção fraca) + dados de teste desatualizados
- **Local:** `tests/integration/test_tableau_real.py::test_integration_metadata_lineage_responde`
  e `.env.integration` (`TABLEAU_IT_DATASOURCE_ID`, IDs de workbook)

### Descrição
O teste de linhagem afirma apenas `status in {"success", "error"}`, ou seja, **passa
mesmo quando a linhagem retorna erro**. Isso mascara regressões reais.

Ao validar manualmente, os IDs configurados em `.env.integration` retornam `NOT_FOUND`:

```
get_downstream_lineage("88cd5bf4-…")  → NOT_FOUND
get_upstream_lineage("b32e69bf-…")    → NOT_FOUND
get_datasource_dictionary("88cd5bf4-…") → NOT_FOUND
```

A Metadata API **não conhece** esses LUIDs. Os LUIDs reais indexados são:
- Workbook "Superstore" = `b2d26c1b-cf2b-4081-945c-7927d541e468`
- "Superstore Datasource" = `18e985e3-e838-469d-a103-bca7aa3dfe92`

Com os LUIDs corretos, as ferramentas funcionam (verificado): downstream/upstream
resolvem o root e o dicionário retorna 34 campos (incl. `Profit Ratio`). Ou seja, **o
produto está correto** — o `NOT_FOUND` é a resposta certa para um LUID inexistente; o
problema é o **dado de teste desatualizado** + a **asserção fraca** que esconde isso.

> Observação: o workbook `b32e69bf` (MCP-Superstore) existe via REST API (inspeção
> estrutural funcionou), mas não aparece na Metadata API — provavelmente não indexado /
> datasource embarcada. A Metadata API lista apenas 4 workbooks no site.

### Correção sugerida
- Atualizar `.env.integration` com LUIDs que existam na Metadata API, **ou** descobrir os
  LUIDs dinamicamente no setup do teste (listar via Metadata API e escolher um).
- Fortalecer a asserção: exigir `status == "success"` (com `direction` correto) para um
  LUID sabidamente existente, mantendo a tolerância a `UPSTREAM_ERROR` apenas para o
  cenário de degradação Cloud/Server (RF24) explicitamente separado.

- **Status:** Corrigido
- **Correção aplicada:** (1) `TABLEAU_IT_DATASOURCE_ID` atualizado em `.env.integration`
  (e `.env`) para o LUID indexado `18e985e3-e838-469d-a103-bca7aa3dfe92` ("Superstore
  Datasource"), com o LUID antigo `88cd5bf4-…` (que retornava `NOT_FOUND`) substituído;
  (2) asserção fortalecida em `test_integration_metadata_lineage_responde`: exige
  `status == "success"` com `direction == "downstream"` e `root` resolvido, tolerando
  apenas `UPSTREAM_ERROR` (degradação RF24) — `NOT_FOUND` passa a falhar o teste.
- **Testes de regressão:**
  `tests/integration/test_tableau_real.py::test_integration_metadata_lineage_responde`
  (asserção reforçada; requer Tableau real via `pytest -m integration`).

# Relatório de Code Review - MCP Tableau

## Resumo
- Data: 2026-06-26
- Branch: main (último commit `d591fab` — "fix(tableau): suporte a CA bundle TLS e tradução de erros de transporte")
- Status: **APROVADO COM RESSALVAS**

> **Atualização pós-review:** o achado de severidade Média e os dois ajustes de
> tipagem foram **corrigidos** após este review (ver § Problemas Encontrados e
> § Correções aplicadas). A suíte subiu para **133/133** com cobertura **93,79%**.
> Permanecem apenas ressalvas de severidade Baixa, não bloqueantes.

Implementação coesa, bem tipada, segura e com cobertura de testes acima da meta.
A suíte rápida está verde (133/133) e o código está em conformidade com as rules do
projeto e, em grande parte, com a TechSpec. As ressalvas remanescentes são **não
bloqueantes**: referem-se a uma simplificação documentada de MVP (QA estrutural sem
combinar a Metadata API) e a uma otimização de performance da heurística visual.

## Conformidade com Rules

### code-standards

| Rule | Status | Observações |
|------|--------|-------------|
| `ruff check` sem erros | OK | `All checks passed!` |
| `ruff format` sem erros | OK | `37 files already formatted` |
| Linha ≤ 88, aspas duplas, f-strings | OK | Consistente em todo o pacote |
| Type hints obrigatórios em funções públicas | OK | Públicas completas. As 2 privadas antes sem hint (`deploy._content_exists`, `client._with_reauth`) foram **corrigidas** após o review; `# type: ignore` removido. |
| Tipos nativos (`list[str]`, `str \| None`) | OK | Sem `Optional`/`List` do `typing` |
| Modelos Pydantic como contrato (não dicts) | OK | Saídas tipadas em `models.py`; exceção consciente: `render_workbook_pdf` devolve `dict` de status simples + bloco `File` (coerente com a TechSpec) |
| Ferramentas finas que delegam | OK | `tools/*` orquestram; regra em `validation/*` e I/O em `tableau/*` |
| Acesso ao Tableau só via `tableau/client.py` | OK | Nenhuma tool instancia o TSC diretamente |
| Docstring-contrato nas ferramentas | OK | Todas as 10 tools documentam args/returns/códigos de erro |
| Credenciais por env; sem segredos no código/log | OK | `SecretStr` no PAT; mensagens de erro construídas sem token; `.env`/`.env.integration` no `.gitignore` (não rastreados) |
| `.env.example` atualizado | OK | Inclui `TABLEAU_CA_BUNDLE`, timeouts e limiares |
| Tratamento de erro específico (não `except Exception` cego) | OK | `_translate`/`_with_reauth` capturam exceções específicas do TSC; `# noqa: BLE001` apenas onde a captura larga é traduzida para erro acionável |

### testing-standards

| Rule | Status | Observações |
|------|--------|-------------|
| `tests/` espelha `src/mcp_tableau/` | OK | Estrutura paralela completa |
| Rede/Tableau sempre mockados em unit | OK | Integração real isolada em `tests/integration/` |
| Integração MCP in-memory na suite rápida | OK | `tests/test_mcp_integration.py` |
| Integração real marcada `@pytest.mark.integration` | OK | 3 testes deselecionados da suite rápida |
| Nomenclatura `test_<unidade>_<cenario>_<resultado>` | OK | Aderente |
| Cobertura ≥ 80% | OK | **93,76%** |

## Aderência à TechSpec

| Decisão Técnica | Implementado | Observações |
|-----------------|--------------|-------------|
| Layout `src/mcp_tableau/` com separação por responsabilidade | SIM | `tools/`, `tableau/`, `validation/`, `models.py`, `config.py`, `server.py` |
| 10 ferramentas MCP (4 capacidades) | SIM | Deploy(2), Visual(2), QA(2), Metadados(4) — todas registradas |
| Camada de integração única (REST) | SIM | `TableauClient` com PAT, re-auth lazy (1 retry), publish/download/render, paginação `Pager` |
| Metadata API (GraphQL) reaproveitando a sessão | SIM | `MetadataClient(client)` usa `.server` autenticado |
| Validação pura sem rede | SIM | `structure/complexity/visual/similarity` puras e testáveis |
| Modelos Pydantic + envelope `ToolError` tipado | SIM | `models.py` cobre todos os contratos; `ErrorCode` enum |
| Chunking transparente >64 MB | SIM | `CHUNK_THRESHOLD_BYTES`, flag `chunked` |
| Recusa de overwrite implícito (RF7) | SIM | `_content_exists` → `OVERWRITE_NOT_ALLOWED` |
| Heurística visual + imagem ao agente multimodal | SIM | `RenderImageResult` + bloco `Image` |
| Re-auth lazy / sign-out garantido (context manager) | SIM | `tableau_session` / `__exit__` |
| Segredos nunca em log/retorno (RF23) | SIM | `SecretStr`, mensagens sanitizadas, tradução TLS/conexão acionável |
| **QA estrutural híbrido (XML + Metadata API p/ campos quebrados resolvidos pelo servidor)** | **PARCIAL** | `tools/qa.py` usa **apenas** parsing XML local; a combinação com a Metadata API foi adiada (NOTA de MVP documentada no módulo). RF13/RF14 ainda atendidos via detecção local. **Ressalva.** |
| `get_upstream_lineage` aceitando `content_type` ("workbook"/"datasource") | SIM (corrigido) | Após o review: `content_type` não suportado é recusado no boundary com `VALIDATION_ERROR` (sem rede), em vez de tratar `"datasource"` como workbook. Suporte a datasource segue como follow-up de MVP. |

## Tasks Verificadas

| Task | Status | Observações |
|------|--------|-------------|
| 1.0 Fundação (config, models, server, deps) | COMPLETA | `config.py`/`models.py`/`server.py`/`main.py` presentes e 100% cobertos |
| 2.0 Integração REST (`tableau/client.py`) | COMPLETA | Auth PAT, re-auth, publish, download, render, busca |
| 3.0 Integração GraphQL (`tableau/metadata.py`) | COMPLETA | Linhagem ↑/↓ e dicionário |
| 4.0 Validação pura (`validation/*`) | COMPLETA | 4 módulos puros com testes |
| 5.0 Tools Deploy | COMPLETA | `publish_workbook`/`publish_datasource` |
| 6.0 Tools Metadados | COMPLETA | 4 tools; `content_type` de upstream corrigido pós-review (`VALIDATION_ERROR`) |
| 7.0 Tools QA | COMPLETA | `inspect`/`audit`; ressalva: Metadata API não combinada (MVP) |
| 8.0 Tools Visual | COMPLETA | `render_view_image`/`render_workbook_pdf` |
| 9.0 Integração MCP in-memory + cobertura ≥80% | COMPLETA | Suite in-memory + 93,76% |

## Testes
- Total de Testes (suite rápida): 133 (132 no review original + 1 regressão pós-correção)
- Passando: 133
- Falhando: 0
- Integração real (marcada, fora da suite rápida): 3 (deselecionados)
- Coverage: **93,79%** (meta ≥ 80%)

```
133 passed, 3 deselected in 2.89s
Required test coverage of 80% reached. Total coverage: 93.79%
```

## Problemas Encontrados

| Severidade | Arquivo | Linha | Descrição | Sugestão | Status |
|------------|---------|-------|-----------|----------|--------|
| Média | `src/mcp_tableau/tools/metadata.py` | 73–108 | `get_upstream_lineage` aceita `content_type` (default `"workbook"`) mas o ignora: sempre chama `upstream_of_workbook`. Passar `"datasource"` é tratado silenciosamente como workbook, levando a resultado incorreto/`NOT_FOUND` sem feedback. | Honrar o parâmetro (rota para upstream de datasource) **ou** rejeitar valores ≠ `"workbook"` com `VALIDATION_ERROR` enquanto não suportado. | **Corrigido** — rejeição com `VALIDATION_ERROR` no boundary + teste de regressão. |
| Baixa | `src/mcp_tableau/tools/deploy.py` | 137–138 | `_content_exists(client, …)` sem type hint no `client` (rule "type hints obrigatórios"). | Anotar `client: TableauClient`. | **Corrigido** — `client: TableauClient`. |
| Baixa | `src/mcp_tableau/tableau/client.py` | 236 | `_with_reauth(self, operation)` sem tipo (com `# type: ignore[no-untyped-def]`). | Tipar `operation: Callable[[], T]` com `TypeVar` para remover o ignore. | **Corrigido** — `Callable[[], T]`; `# type: ignore` removido. |
| Baixa | `src/mcp_tableau/tools/qa.py` | 10–16, 55–62 | QA estrutural não combina a Metadata API para campos quebrados resolvidos pelo servidor (RF14), divergindo da TechSpec; decisão de MVP documentada como NOTA. | Manter no MVP; registrar como follow-up para fechar a lacuna de "quebra resolvida no servidor" via Metadata API. | Aberto (follow-up de MVP). |
| Baixa | `src/mcp_tableau/validation/visual.py` | 88 | `rgb.getcolors(maxcolors=total)` força contagem exata de até `width*height` cores; em renders de alta resolução pode custar memória/tempo. | Limitar a contagem (amostragem/redução) ou definir um teto de `maxcolors` razoável antes do fallback. | Aberto (follow-up). |

> Sem problemas de segurança identificados: nenhum segredo no código, PAT em `SecretStr`,
> mensagens de erro sanitizadas e `.env*` fora do versionamento.

## Correções aplicadas (pós-review)

| Achado | Correção | Arquivo(s) |
|--------|----------|------------|
| `content_type` ignorado em `get_upstream_lineage` (Média) | Validação no boundary (antes de qualquer rede): `content_type ∉ {"workbook"}` → `ToolError(VALIDATION_ERROR)` com mensagem acionável; constante `_UPSTREAM_CONTENT_TYPES` e docstring atualizadas. Teste de regressão `test_get_upstream_lineage_content_type_nao_suportado_retorna_validation_error` confirma a rejeição sem instanciar o `MetadataClient`. | `src/mcp_tableau/tools/metadata.py`, `tests/tools/test_metadata.py` |
| `_content_exists(client, …)` sem type hint (Baixa) | Anotado `client: TableauClient` (import adicionado). | `src/mcp_tableau/tools/deploy.py` |
| `_with_reauth(self, operation)` sem tipo + `# type: ignore` (Baixa) | `operation: Callable[[], T]) -> T` com `TypeVar` `T`; `# type: ignore[no-untyped-def]` removido. | `src/mcp_tableau/tableau/client.py` |

Validação das correções: `ruff check` + `ruff format --check` limpos; **133 passed / 0
failed**, cobertura **93,79%**.

## Pontos Positivos
- Arquitetura em camadas limpa e fiel à TechSpec: `validation/*` puro, `tableau/*` sem regra de negócio, `tools/*` finas.
- Envelope de erro tipado (`ToolError`/`ErrorCode`) consistente em todas as ferramentas, com mensagens acionáveis e sem vazamento de credenciais.
- Tradução de erros de transporte (TLS/conexão) acionável (BUG-02), com config opcional `TABLEAU_CA_BUNDLE` — boa resposta a ambiente corporativo.
- Re-autenticação lazy com retry único e sign-out garantido via context manager.
- Cobertura alta (93,79%) com pirâmide de testes correta (unit > MCP in-memory > integração real marcada).
- Shim de `distutils.version.LooseVersion` para Python ≥ 3.12 bem isolado e documentado (porquê, não o quê).
- Docstrings-contrato claras, escritas para quem chama a ferramenta.

## Recomendações
1. ~~Resolver o `content_type` de `get_upstream_lineage`~~ — **Feito** (rejeição com `VALIDATION_ERROR`). Avaliar, em iteração futura, suporte real a upstream de datasource (query GraphQL distinta de tabelas/bancos).
2. Abrir follow-up para fechar a parte híbrida do QA estrutural (Metadata API) prevista na TechSpec, ou atualizar a TechSpec para refletir a decisão de MVP. (Aberto)
3. ~~Completar os type hints das duas funções privadas e remover o `# type: ignore`~~ — **Feito**.
4. Avaliar o custo de `getcolors` em renders grandes na heurística visual. (Aberto)

## Conclusão
**APROVADO COM RESSALVAS.** O código atende às rules do projeto (ruff limpo, tipagem,
segurança de credenciais, modelos Pydantic, ferramentas finas), implementa as 9 tasks e
as 4 capacidades, e a suíte rápida está verde com cobertura de 93,79% — acima da meta de
80%. O achado de severidade Média (`content_type` ignorado em `get_upstream_lineage`) e
os dois ajustes de tipagem foram **corrigidos após o review**, com teste de regressão
(ver § Correções aplicadas). As ressalvas remanescentes são de severidade Baixa e não
bloqueantes: a simplificação documentada do QA estrutural (XML-only) e a otimização de
`getcolors` na heurística visual, ambas registradas como follow-up. Nenhum teste falha e
nenhum problema de segurança foi identificado.

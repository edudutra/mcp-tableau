# Tarefa 9.0: Integração MCP in-memory e cobertura ≥80%

## Visão geral

Fecha a feature validando o servidor de ponta a ponta no nível do protocolo e garantindo a meta
de qualidade. Sobe o `FastMCP` em processo (in-memory) e chama as ferramentas via cliente de
teste, com `TableauClient`/`MetadataClient` mockados, verificando descoberta de ferramentas,
contratos de entrada/saída, serialização do `ToolError` e presença de docstrings. Marca os testes
de integração com Tableau real (`@pytest.mark.integration`) fora da suite rápida e assegura
cobertura global ≥80% (`--cov=mcp_tableau --cov-fail-under=80`). Atualiza documentação de execução.

<skills>
### Conformidade com skills

- **`testing-standards`** — pirâmide (unitários mockando rede, integração MCP in-memory,
  integração real marcada), meta de cobertura ≥80%, estrutura de `tests/` espelhando o `src`.
- **`code-standards`** — todas as ferramentas com docstring-contrato; `ruff` sem violações.
</skills>

<requirements>
- **RF22**: Toda ferramenta retorna estrutura tipada com status explícito (verificação global).
- **RF23**: Falhas retornam `ToolError` serializado e acionável.
- **RF24**: Integração real marcada cobre Cloud/Server (degradação para `null`/`UPSTREAM_ERROR`).
- Meta de qualidade: cobertura ≥80%.
</requirements>

## Subtarefas

- [x] 9.1 Implementar a suite de integração MCP in-memory (todas as tools registradas mockando as
  camadas `tableau/*`).
- [x] 9.2 Marcar e isolar testes de integração com Tableau real (`@pytest.mark.integration`) fora
  da suite rápida (publish/download roundtrip, render PNG, lineage).
- [x] 9.3 Configurar `pytest-cov` com `--cov=mcp_tableau --cov-fail-under=80` e fechar lacunas de
  cobertura.
- [x] 9.4 Atualizar `AGENTS.md`/`README.md` com dependências e instruções de execução do servidor.

## Detalhes de implementação

Ver techspec.md § "Abordagem de testes" (testes de integração MCP in-memory, integração real
marcada, E2E smoke opcional), § "Dependências técnicas" e § "Arquivos relevantes e dependentes".

## Critérios de sucesso

- Todas as ferramentas são descobríveis e expõem docstrings.
- Contrato de entrada/saída serializa corretamente via MCP in-memory.
- Ferramenta em erro retorna `ToolError` serializado.
- Testes de integração real marcados com `@pytest.mark.integration` e fora da suite rápida.
- Cobertura ≥80% (`--cov-fail-under=80`) atendida; documentação atualizada.

## Testes da tarefa

### Testes unitários

- [ ] (Não aplicável — unitários ficam nas tarefas de origem; aqui o foco é integração e
  cobertura agregada.)

### Testes de integração

Integração MCP in-memory (suite rápida):
- [x] `test_mcp_todas_ferramentas_registradas_e_descobriveis`
- [x] `test_mcp_publish_workbook_contrato_de_entrada_e_saida_serializa`
- [x] `test_mcp_render_view_image_retorna_bloco_imagem_e_json`
- [x] `test_mcp_ferramenta_em_erro_retorna_toolerror_serializado`
- [x] `test_mcp_docstrings_presentes_em_todas_ferramentas`

Integração com Tableau real (`@pytest.mark.integration`, fora da suite rápida):
- [x] `test_integration_publish_e_download_roundtrip`
- [x] `test_integration_render_view_image_retorna_png_valido`
- [x] `test_integration_metadata_lineage_responde`

### Testes E2E (se aplicável)

- [ ] Smoke opcional em pipeline dedicado (descobrir → publicar → validar → inspecionar contra
  sandbox). Playwright não se aplica (produto sem UI).

## Arquivos relevantes

- `tests/test_mcp_integration.py`
- `tests/integration/test_tableau_real.py`
- `pyproject.toml` (config de cobertura)
- `AGENTS.md`
- `README.md`

# Relatório de Code Review — Enriquecer Saídas com IDs

## Resumo

- Data: 2026-06-27
- Branch: main
- Status: **APROVADO COM RESSALVAS** (ressalvas de baixa severidade, sem bloqueio)

---

## Conformidade com Rules

| Rule | Status | Observações |
|------|--------|-------------|
| Type hints completos | OK | Todos os métodos e funções com anotações completas |
| Modelos Pydantic para contratos de saída | OK | `SheetRef` adicionado corretamente em `models.py` |
| Validação pura sem rede | OK | `inspect_structure` permanece sem dependência de rede (verificado por teste dedicado) |
| Ferramenta fina orquestrando | OK | `tools/qa.py` delega parsing a `validation/structure.py` e REST a `tableau/client.py` |
| Acesso ao Tableau exclusivamente via `tableau/client.py` | OK | Nenhuma chamada TSC direta em `tools/` ou `validation/` |
| Sem credenciais em logs/mensagens de erro | OK | `_enrich_with_view_luids` loga apenas `workbook_id` e `exc.code.value`; sem PAT/token |
| Nomes de teste `test_<unidade>_<cenário>_<resultado>` | OK | Todos os 28 novos testes seguem o padrão |
| Cobertura ≥ 80% | OK | 93,46% total (`mcp_tableau`) — bem acima da meta |

---

## Aderência à TechSpec

| Decisão Técnica | Implementado | Observações |
|-----------------|--------------|-------------|
| LUID obtido via REST `populate_views` (não Metadata API) | SIM | `list_workbook_view_luids` usa `workbooks.get_by_id` + `populate_views` |
| Enriquecimento na camada de ferramenta; parsing puro intocado | SIM | `_enrich_with_view_luids` em `tools/qa.py`; `validation/structure.py` sem rede |
| Degradação best-effort: falha → `id=null`, `status="success"` | SIM | `except TableauClientError` em `_enrich_with_view_luids`, log WARNING |
| Quebra de contrato `list[str]` → `list[SheetRef]` sem camada de compatibilidade | SIM | `ValidationError` levantada ao passar `list[str]` (teste confirma) |
| RF5 (id de conexão) adiado | SIM | `ConnectionInfo` inalterada; teste `test_connection_info_inalterada` guarda comportamento |
| RF11: verificação de consistência em similaridade/linhagem | SIM | `test_rf11_id_consistente_em_similaridade_e_linhagem` verifica `id: str` em `SimilarityMatch`, `LineageNode`, `ContentRef` |
| Log WARNING em falha de enriquecimento | SIM | `logger.warning(...)` com `workbook_id` e `exc.code.value` |
| Log DEBUG com contagem de sheets sem LUID | SIM | `logger.debug(...)` após merge bem-sucedido |
| `_with_reauth` reutilizado no novo método | SIM | `list_workbook_view_luids` envolve `op()` em `_with_reauth` |
| Sem nova dependência, sem nova variável de ambiente | SIM | `tableauserverclient` já provê `populate_views`; `.env.example` inalterado |

---

## Tasks Verificadas

| Task | Status | Observações |
|------|--------|-------------|
| 1.0 Modelos de dados (`SheetRef`, `StructureReport`, `FilterInfo`) | COMPLETA | `SheetRef`, `worksheets: list[SheetRef]`, `dashboards: list[SheetRef]`, `FilterInfo.worksheet_id` implementados |
| 2.0 Validação pura (`structure.py`, `complexity.py`) | COMPLETA | `SheetRef(name=name)` emitido com `id=None`; `complexity.py` usa `len()` — nenhuma mudança necessária |
| 3.0 Cliente REST (`list_workbook_view_luids`) | COMPLETA | Método implementado, 6 testes unitários cobrem: mapa nome→LUID, omissão sem LUID, duplicatas, re-auth, 404, sem vazamento |
| 4.0 Orquestração QA (enriquecimento best-effort e contrato) | COMPLETA | `_enrich_with_view_luids` implementado, 8 testes cobrem encadeamento, degradação e não-regressão |
| 5.0 Integração MCP, RF11, cobertura | COMPLETA | 3 testes MCP in-memory (SheetRef serializado, degradado, encadeamento render); RF11 verificado; cobertura 93,46% |

---

## Testes

- Total de Testes: 165
- Passando: 165
- Falhando: 0
- Coverage total: **93,46%** (meta ≥ 80% — atingida)
- Testes de integração real (marcados `@pytest.mark.integration`): 4/4 passaram (QA anterior)

---

## Problemas Encontrados

| Severidade | Arquivo | Linha | Descrição | Sugestão |
|------------|---------|-------|-----------|----------|
| Baixa | `src/mcp_tableau/validation/structure.py` | 147–148 | Comentário referencia "Tarefa 4.0" e "Tarefa 7.0" — informação efêmera ligada à tarefa que rota com o tempo e não descreve o *porquê* | Substituir por nota técnica pura: `# LUIDs nascem nulos: parsing é puro. A ferramenta preenche por correspondência de nome.` |
| Baixa | `src/mcp_tableau/tools/qa.py` | 101–104 | Branch `except StructureParseError` em `audit_workbook_complexity` não tem teste dedicado (lines 101-104 marcados como `Miss` no relatório de cobertura) | Adicionar `test_audit_workbook_complexity_arquivo_invalido_retorna_upstream_error` espelhando o teste equivalente de `inspect_workbook_structure` |

---

## Pontos Positivos

- **Pureza preservada**: `validation/structure.py` permanece 100% sem rede — verificado por `test_inspect_structure_permanece_puro_sem_rede` que bloqueia qualquer `socket.socket`.
- **Degradação robusta**: o bloco best-effort em `_enrich_with_view_luids` captura `TableauClientError` (único tipo que `_with_reauth` propaga), garantindo que qualquer falha REST degrade para `id=null` sem mudar o `status`.
- **Segurança verificável**: `test_list_workbook_view_luids_nao_vaza_credenciais` garante que PAT name e secret não aparecem em mensagens de erro do novo método.
- **Encadeamento validado end-to-end**: `test_render_aceita_id_do_structure_report` (in-memory) e `test_real_inspect_structure_retorna_luids_validos` (integração real) provam RF3 de ponta a ponta.
- **Breaking change documentado**: docstring de `inspect_workbook_structure` detalha `{id, name}`, degradação best-effort e semântica de `null` — cumpre RF9 sem prolixidade.
- **RF11 coberto por teste estático**: verificação dos campos `id: str` em modelos de similaridade/linhagem é um teste de contrato que falha imediatamente se alguém mudar o tipo por engano.
- **Logging balanceado**: WARNING somente em falha real de enriquecimento; DEBUG para contagem de sheets sem LUID — ruído controlado.

---

## Recomendações

1. **[Baixa — não bloqueante]** Remover referências a "Tarefa 4.0"/"Tarefa 7.0" do comentário em `structure.py:147`. Comentários devem explicar o *porquê*, não referenciar tickets.
2. **[Baixa — não bloqueante]** Adicionar teste para o branch `except StructureParseError` de `audit_workbook_complexity` (`qa.py:101-104`) para fechar a única lacuna de cobertura identificável no relatório de miss.

---

## Conclusão

A implementação está correta, segura e bem testada. Todos os 10 RFs no escopo foram implementados (RF5 adiado por decisão de produto registrada na TechSpec). A arquitetura respeita as decisões da TechSpec em todos os pontos centrais: pureza do parser, enriquecimento best-effort na camada de ferramenta, e degradação sem novos erros. Os 165 testes passam com 93,46% de cobertura. As duas ressalvas identificadas são de baixa severidade (estilo de comentário e lacuna de cobertura em branch já testado de forma análoga) e não comprometem a qualidade nem a segurança da entrega.

**Veredito: APROVADO COM RESSALVAS** — ambas as ressalvas são melhorias opcionais, sem impacto em funcionalidade, segurança ou contrato.

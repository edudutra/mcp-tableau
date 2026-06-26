# Tarefa 4.0: Camada de validação pura (`validation/*`)

## Visão geral

Implementa as quatro funções puras de validação que não conhecem rede nem o TSC e dependem
apenas dos modelos da Tarefa 1.0: parsing estrutural do XML do workbook
(`validation/structure.py`), auditoria de complexidade contra limiares
(`validation/complexity.py`), heurística de detecção de tela em branco com Pillow
(`validation/visual.py`) e correspondência fuzzy de similaridade com `rapidfuzz`
(`validation/similarity.py`). Por serem puras, são testáveis sem mocks de rede e podem ser
construídas em paralelo às camadas de integração.

<skills>
### Conformidade com skills

- **`code-standards`** — funções puras isoladas de rede, type hints, modelos Pydantic como
  contrato de saída, estilo ruff.
- **`testing-standards`** — fixtures `.twbx`/`.twb` em `tmp_path`, imagens sintéticas em memória,
  `parametrize` para limiares, nomenclatura padrão.
</skills>

<requirements>
- **RF11**: Sinalizar indícios de erro visual (tela/gráfico em branco) de forma estruturada
  (`detect_blank_render`).
- **RF14**: Identificar campos quebrados, filtros sem lógica e conexões inválidas
  (`inspect_structure`).
- **RF15/RF16**: Auditar indicadores de complexidade contra limiares e avaliar conformidade
  (`audit_complexity`).
- **RF20**: Pesquisar conteúdo semelhante por correspondência fuzzy (`rank_similar`).
</requirements>

## Subtarefas

- [x] 4.1 `validation/structure.py` — `inspect_structure(path)`: parse de `.twb`/`.twbx` via
  `tableaudocumentapi`; extrair worksheets, dashboards, conexões, campos (com fórmula) e
  filtros; detectar campos quebrados, filtros sem lógica e conexões inválidas como `issues`
  (sem falhar); tratar XML corrompido com erro tratável.
- [x] 4.2 `validation/complexity.py` — `audit_complexity(report, thresholds)`: comparar métricas
  contra limiares, acumular `findings` e definir `compliant`; valores no limite exato não geram
  finding.
- [x] 4.3 `validation/visual.py` — `detect_blank_render(image_bytes)`: heurística de
  uniformidade/branco com Pillow retornando `VisualDiagnostic` (`is_likely_blank`,
  `blank_ratio` 0–1, `severity`, `message`); bytes inválidos levantam erro tratável.
- [x] 4.4 `validation/similarity.py` — `rank_similar(term, candidates, limit)`: ranking fuzzy
  decrescente por `score`, match exato com score máximo, case/acento-insensível, respeitando
  `limit`; lista vazia quando sem candidatos.

## Detalhes de implementação

Ver techspec.md § "Camada de validação" (assinaturas), § "Modelos de dados"
(`StructureReport`, `StructureIssue`, `ComplexityReport`, `VisualDiagnostic`, `SimilarityMatch`)
e § "Principais decisões" (QA híbrido, inspeção visual em duas camadas, similaridade fuzzy).

## Critérios de sucesso

- Workbook `.twbx` compactado e `.twb` puro produzem a mesma estrutura.
- Campo calculado com referência inexistente é marcado como `broken_field`; filtro sem lógica
  gera `issue` de `warning`; nenhuma issue não falha a função.
- `blank_ratio` sempre entre 0.0 e 1.0; `severity="error"` acima do limiar configurável.
- Ranking de similaridade ordenado por score; match exato no topo; `limit` respeitado.
- Entradas malformadas (XML corrompido, bytes inválidos) levantam erro tratável, não crash.

## Testes da tarefa

### Testes unitários

`validation/structure.py`:
- [x] `test_inspect_structure_workbook_valido_lista_worksheets_e_dashboards`
- [x] `test_inspect_structure_extrai_campos_calculados_com_formula`
- [x] `test_inspect_structure_campo_calculado_referencia_inexistente_marca_broken_field`
- [x] `test_inspect_structure_filtro_sem_logica_gera_issue_warning`
- [x] `test_inspect_structure_conexao_invalida_gera_issue`
- [x] `test_inspect_structure_workbook_sem_issues_retorna_lista_vazia`
- [x] `test_inspect_structure_twbx_compactado_e_twb_puro_produzem_mesma_estrutura`
- [x] `test_inspect_structure_arquivo_xml_corrompido_levanta_erro_tratavel`

`validation/complexity.py`:
- [x] `test_audit_complexity_dentro_dos_limiares_compliant_true`
- [x] `test_audit_complexity_excesso_de_filtros_gera_finding_warning`
- [x] `test_audit_complexity_excesso_de_worksheets_gera_finding`
- [x] `test_audit_complexity_multiplos_estouros_acumula_findings`
- [x] `test_audit_complexity_thresholds_customizados_alteram_resultado`
- [x] `test_audit_complexity_valores_no_limite_exato_nao_geram_finding`

`validation/visual.py`:
- [x] `test_detect_blank_render_imagem_uniforme_branca_is_likely_blank_true`
- [x] `test_detect_blank_render_imagem_com_conteudo_is_likely_blank_false`
- [x] `test_detect_blank_render_blank_ratio_entre_zero_e_um`
- [x] `test_detect_blank_render_severity_error_quando_acima_do_limiar`
- [x] `test_detect_blank_render_bytes_invalidos_levanta_erro_tratavel`

`validation/similarity.py`:
- [x] `test_rank_similar_ordena_por_score_decrescente`
- [x] `test_rank_similar_match_exato_score_maximo`
- [x] `test_rank_similar_sem_candidatos_retorna_lista_vazia`
- [x] `test_rank_similar_respeita_limit`
- [x] `test_rank_similar_case_insensitive_e_acentos`

### Testes de integração

- [x] Não aplicável (funções puras; integração das tools coberta nas Tarefas 7.0/8.0/6.0 e 9.0).

## Arquivos relevantes

- `src/mcp_tableau/validation/__init__.py`
- `src/mcp_tableau/validation/structure.py`
- `src/mcp_tableau/validation/complexity.py`
- `src/mcp_tableau/validation/visual.py`
- `src/mcp_tableau/validation/similarity.py`
- `tests/validation/test_structure.py`
- `tests/validation/test_complexity.py`
- `tests/validation/test_visual.py`
- `tests/validation/test_similarity.py`

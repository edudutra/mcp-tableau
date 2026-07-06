# Tarefa 8.0: Fechamento — testes de integração reais e documentação

## Visão geral

Fechar a feature com os testes de integração contra o runtime Hyper real (`tests/integration/test_hyper_real.py`, `@pytest.mark.integration`), que cobrem a métrica de sucesso do PRD ("CSV → `.hyper` → datasource publicado" de ponta a ponta), e com a documentação de operação: `.env.example` (seção `# Hyper`), README/QUICKSTART (Capacidade 5, instalação de drivers de banco, ciclo de vida e limpeza dos `.hyper` locais). Verificação final de qualidade: `ruff` e gate de cobertura ≥ 80%.

<skills>
### Conformidade com skills

- `testing-standards` — testes `integration` com runtime real e arquivos em `tmp_path` (sem binários versionados), fixtures `sample_hyper` e `hyper_env` em `conftest.py`, separação suite rápida × `-m integration`.
- `code-standards` — documentação em português no padrão do repositório, exemplo de configuração sem credenciais reais no `.env.example`.
</skills>

<requirements>
- Métrica de sucesso do PRD: fluxo "CSV → `.hyper` → datasource publicado" completado de ponta a ponta em ambiente de homologação.
- RF25 — defaults conservadores dos limiares documentados.
- Restrição de privacidade do PRD: ciclo de vida (localização e limpeza) dos `.hyper` intermediários documentado (decisão 4 da techspec — enforcement por documentação).
- Restrição da techspec: drivers de banco instalados à parte pelo administrador, documentados no README.
</requirements>

## Subtarefas

- [x] 8.1 Criar `tests/integration/test_hyper_real.py` com os casos 87–92 (runtime Hyper real; 87–91 offline, 92 requer credenciais Tableau do `.env` real).
- [x] 8.2 Adicionar a `tests/conftest.py` a fixture `sample_hyper` (constrói `.hyper` mínimo sob demanda, reuso apenas nos testes `integration`); CSVs gerados em `tmp_path` pelas próprias fixtures.
- [x] 8.3 Atualizar `.env.example` com a seção `# Hyper`: limiares (`HYPER_MAX_SOURCE_FILE_MB`, `HYPER_MAX_INLINE_ROWS`, `HYPER_MAX_RESULT_ROWS`, `HYPER_MAX_EXTRACT_ROWS`) e exemplo comentado de `HYPER_DB_CONN_<NOME>`.
- [x] 8.4 Atualizar README (Capacidade 5 — Hyper Datasources: as 7 tools, configuração de conexões nomeadas, instalação de drivers por fonte, ciclo de vida/limpeza dos `.hyper` com recomendação de diretório dedicado) e QUICKSTART (dependência `tableauhyperapi` com runtime binário ~150 MB e plataformas suportadas).
- [x] 8.5 Rodar verificação final: `uv run pytest` (suite rápida, `--cov-fail-under=80`), `uv run pytest -m integration` em homologação e `ruff` sem apontamentos.

## Detalhes de implementação

Ver techspec.md, seções "Testes de integração" e "Testes E2E" em "Abordagem de testes" (requisitos de dados de teste), item 7 de "Ordem de construção", "Riscos conhecidos" (tamanho/portabilidade do runtime) e decisão 4 ("paths livres — ciclo de vida documentado no README") em "Principais decisões".

## Critérios de sucesso

- Casos 87–91 verdes offline com runtime Hyper real; caso 92 verde em homologação com credenciais.
- Fluxo completo da métrica do PRD demonstrado pelo caso 87 + 92 (`uv run pytest -m integration`).
- `.env.example`, README e QUICKSTART atualizados: um administrador consegue configurar conexões, limiares e drivers apenas com a documentação.
- Gate de cobertura ≥ 80% mantido na suite rápida; `ruff` limpo; nenhum arquivo binário de teste versionado.

## Testes da tarefa

### Testes unitários

- Não aplicável (cobertos nas tarefas 1.0–7.0).

### Testes de integração

`tests/integration/test_hyper_real.py` (casos 87–92 da techspec, `@pytest.mark.integration`, arquivos em `tmp_path`):

- [x] 87. `test_ciclo_completo_csv_para_hyper_query_e_inspecao` (cria CSV → `.hyper` → inspeciona → consulta → confere contagens; usa `schema` explícito — CSV não é inferível pelo runtime, ver nota abaixo)
- [x] 88. `test_ciclo_inline_criar_append_e_derivar_tabela`
- [x] 89. `test_parquet_para_hyper_com_inferencia_de_schema`
- [x] 90. `test_update_e_delete_refletem_no_row_count`
- [x] 91. `test_extract_database_para_hyper_com_sqlite_local` (SQLAlchemy + SQLite em `tmp_path` como banco externo real)
- [x] 92. `test_publicacao_hyper_no_tableau_real` (requer credenciais; pulado offline, verde em homologação)

## Achados dos testes de integração (runtime real)

Os testes contra o runtime real do `tableauhyperapi` revelaram defeitos que os
unitários (com `hapi` falso) não pegavam:

1. **Identificadores citados vazando no contrato (corrigido nesta tarefa).** O
   `Name` do Hyper serializa citado em `str()` (ex.: `"cidade"`), então
   `inspect_hyper_schema`/`query_hyper` retornavam nomes de coluna/tabela com
   aspas, e `append_to_hyper` inline sempre falhava com `HYPER_SCHEMA_MISMATCH`
   (comparava `produto` contra `"produto"`). Corrigido com o helper
   `engine._identifier` (usa `.unescaped`) em `_column_from_sql`, `_leaf_name` e
   `_assert_compatible`; guardado por teste unitário na suite rápida.
2. **Inferência de schema de CSV não suportada pelo runtime (defeito em aberto,
   fora do escopo desta tarefa).** `create_hyper_from_file` sem `schema` para CSV
   monta `CREATE TABLE ... AS SELECT * FROM external(..., FORMAT => 'csv')`, que o
   Hyper rejeita: *"EXTERNAL scan of type csv cannot have its schema inferred"*.
   Só Parquet embarca schema (caso 89 cobre a inferência). **Recomendação:** abrir
   bugfix para (a) implementar inferência de CSV (ler cabeçalho + amostrar tipos e
   montar a `DESCRIPTOR`/`COPY`) ou (b) exigir `schema` para CSV com erro
   acionável. O caso 87 usa `schema` explícito (caminho `COPY FROM`, confiável).

### Testes E2E (se aplicável)

- O fluxo ponta a ponta "CSV → `.hyper` → datasource publicado" é coberto pelos casos 87 e 92 executados em homologação com `uv run pytest -m integration` (não há frontend).

## Arquivos relevantes

- `tests/integration/test_hyper_real.py` — novo
- `tests/conftest.py` — modificado (fixtures `sample_hyper`, `hyper_env`)
- `.env.example` — modificado (seção `# Hyper`)
- `README.md` — modificado (Capacidade 5, drivers, ciclo de vida dos `.hyper`)
- `QUICKSTART.md` — modificado (runtime Hyper, plataformas)

"""Integração com o runtime Hyper real (fora da suite rápida).

Casos 87–92 da techspec: exercitam o ciclo de vida completo de `.hyper` contra o
runtime real do `tableauhyperapi` (e, no caso 91, contra um SQLite local via
SQLAlchemy). Cobrem a métrica de sucesso do PRD — "CSV → `.hyper` → datasource
publicado" — ponta a ponta.

Características:

- Marcados com ``@pytest.mark.integration`` (fora da suite rápida; rode com
  ``uv run pytest -m integration``).
- Pulam automaticamente quando o runtime Hyper (`tableauhyperapi`) não está
  instalado — os binários pesam ~150 MB e não entram na CI padrão.
- Os casos **87–91 rodam offline** (sem rede): as credenciais TABLEAU_* fictícias
  do fixture `hyper_offline_env` só satisfazem `load_settings()`; nenhum sign-in
  ocorre. Todos os arquivos vivem em ``tmp_path`` (nada binário versionado).
- O caso **92 requer credenciais Tableau reais** (o `.env` de homologação) e um
  projeto de sandbox; é pulado sem ``TABLEAU_INTEGRATION=1``.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from mcp_tableau.hyper.engine import InlineIngestRequest, hapi, hyper_session
from mcp_tableau.models import (
    HyperCreateResult,
    HyperMutationResult,
    HyperQueryResult,
    HyperSchemaReport,
    InlineColumn,
    PublishResult,
)
from mcp_tableau.tools import deploy, hyper

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        hapi is None, reason="Runtime Hyper (tableauhyperapi) não instalado."
    ),
]

# Credenciais fictícias (nunca usadas — os casos offline não fazem sign-in) e
# limiares altos para não disparar VolumeAlert com os dados minúsculos dos testes.
_HYPER_OFFLINE_ENV = {
    "TABLEAU_SERVER_URL": "https://tableau.example.com",
    "TABLEAU_SITE": "acme",
    "TABLEAU_PAT_NAME": "ci-token",
    "TABLEAU_PAT_SECRET": "nao-usado-offline",
    "HYPER_MAX_SOURCE_FILE_MB": "500",
    "HYPER_MAX_INLINE_ROWS": "1000",
    "HYPER_MAX_RESULT_ROWS": "1000",
    "HYPER_MAX_EXTRACT_ROWS": "5000000",
}


@pytest.fixture
def hyper_offline_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Satisfaz `load_settings()` nos casos offline sem depender do `.env` real.

    As tools de Hyper chamam `load_settings()`, que exige as variáveis TABLEAU_*.
    Injetamos valores fictícios (nenhum sign-in acontece nos casos 87–91) e
    limiares altos. Variáveis de ambiente têm precedência sobre o `.env`, então o
    comportamento é determinístico mesmo em homologação.
    """
    for key, value in _HYPER_OFFLINE_ENV.items():
        monkeypatch.setenv(key, value)


def _export_parquet_via_hyper(tmp_path: Path) -> Path:
    """Gera um `.parquet` real exportando um `.hyper` mínimo via `COPY ... TO`.

    Evita depender de `pyarrow`/`pandas`: o próprio runtime Hyper escreve o
    Parquet, que o caso 89 relê com inferência de schema.
    """
    src = tmp_path / "parquet_src.hyper"
    parquet = tmp_path / "dados.parquet"
    with hyper_session() as engine:
        engine.create_table_from_rows(
            InlineIngestRequest(
                hyper_path=src,
                table_name="Extract",
                columns=[
                    InlineColumn(name="cidade", type="text"),
                    InlineColumn(name="vendas", type="big_int"),
                ],
                rows=[["Santos", 100], ["Sao Paulo", 200]],
            )
        )
        literal = str(parquet).replace("'", "''")
        engine.execute(
            src,
            f"COPY \"Extract\".\"Extract\" TO '{literal}' WITH (FORMAT => 'parquet')",
        )
    return parquet


# -- 87: ciclo completo CSV → .hyper → inspeção → consulta ---------------------


def test_ciclo_completo_csv_para_hyper_query_e_inspecao(
    tmp_path: Path, hyper_offline_env: None
) -> None:
    """CSV → `.hyper` → inspeção → consulta, conferindo contagens.

    Usa `schema` explícito (caminho `COPY FROM`): o runtime Hyper **não** infere o
    schema de CSV via `external()` (só Parquet embarca schema — ver caso 89), de
    modo que o schema explícito é o caminho confiável para CSV.
    """
    csv = tmp_path / "vendas.csv"
    csv.write_text(
        "cidade,vendas\nSantos,100\nSao Paulo,200\nRio,300\n", encoding="utf-8"
    )
    dest = tmp_path / "vendas.hyper"
    schema = [
        InlineColumn(name="cidade", type="text"),
        InlineColumn(name="vendas", type="big_int"),
    ]

    created = hyper.create_hyper_from_file(str(csv), str(dest), schema=schema)
    assert isinstance(created, HyperCreateResult), created
    assert created.source == "csv"
    assert created.row_count == 3
    assert {col.name for col in created.columns} == {"cidade", "vendas"}
    assert dest.is_file()

    report = hyper.inspect_hyper_schema(str(dest))
    assert isinstance(report, HyperSchemaReport), report
    assert len(report.tables) == 1
    table = report.tables[0]
    assert table.schema_name == "Extract"
    assert table.table_name == "Extract"
    assert table.row_count == 3
    assert {col.name for col in table.columns} == {"cidade", "vendas"}

    result = hyper.query_hyper(
        str(dest), 'SELECT cidade, vendas FROM "Extract"."Extract" ORDER BY vendas'
    )
    assert isinstance(result, HyperQueryResult), result
    assert result.row_count == 3
    assert result.truncated is False
    assert result.rows[0] == ["Santos", 100]


# -- 88: inline → append → derivar tabela --------------------------------------


def test_ciclo_inline_criar_append_e_derivar_tabela(
    tmp_path: Path, hyper_offline_env: None
) -> None:
    """Cria tabela inline, faz append inline e deriva outra via CREATE TABLE AS."""
    dest = tmp_path / "inline.hyper"
    columns = [
        InlineColumn(name="produto", type="text"),
        InlineColumn(name="qtd", type="big_int"),
    ]

    created = hyper.create_hyper_from_inline(
        str(dest), "Vendas", columns, [["A", 1], ["B", 2]]
    )
    assert isinstance(created, HyperCreateResult), created
    assert created.source == "inline"
    assert created.row_count == 2

    appended = hyper.append_to_hyper(
        str(dest), "Vendas", columns=columns, rows=[["C", 3]]
    )
    assert isinstance(appended, HyperMutationResult), appended
    assert appended.operation == "append"
    assert appended.affected_rows == 1

    derived = hyper.execute_hyper_sql(
        str(dest),
        'CREATE TABLE "Extract"."Resumo" AS SELECT produto FROM "Extract"."Vendas"',
    )
    assert isinstance(derived, HyperMutationResult), derived
    assert derived.operation == "create_table_as"
    assert derived.table_name == "Resumo"

    report = hyper.inspect_hyper_schema(str(dest))
    assert isinstance(report, HyperSchemaReport), report
    counts = {table.table_name: table.row_count for table in report.tables}
    assert counts["Vendas"] == 3
    assert counts["Resumo"] == 3


# -- 89: Parquet → .hyper com inferência de schema -----------------------------


def test_parquet_para_hyper_com_inferencia_de_schema(
    tmp_path: Path, hyper_offline_env: None
) -> None:
    """Lê um `.parquet` real inferindo o schema e confere colunas/linhas."""
    parquet = _export_parquet_via_hyper(tmp_path)
    dest = tmp_path / "from_parquet.hyper"

    created = hyper.create_hyper_from_file(str(parquet), str(dest))
    assert isinstance(created, HyperCreateResult), created
    assert created.source == "parquet"
    assert {col.name for col in created.columns} == {"cidade", "vendas"}

    report = hyper.inspect_hyper_schema(str(dest))
    assert isinstance(report, HyperSchemaReport), report
    assert report.tables[0].row_count == 2


# -- 90: UPDATE e DELETE refletem no row_count ---------------------------------


def test_update_e_delete_refletem_no_row_count(
    tmp_path: Path, hyper_offline_env: None
) -> None:
    """UPDATE/DELETE retornam linhas afetadas e a contagem final bate na inspeção."""
    dest = tmp_path / "mut.hyper"
    columns = [
        InlineColumn(name="id", type="big_int"),
        InlineColumn(name="status", type="text"),
    ]
    hyper.create_hyper_from_inline(
        str(dest), "Itens", columns, [[1, "novo"], [2, "novo"], [3, "novo"]]
    )

    updated = hyper.execute_hyper_sql(
        str(dest), 'UPDATE "Extract"."Itens" SET status = \'ativo\' WHERE id <= 2'
    )
    assert isinstance(updated, HyperMutationResult), updated
    assert updated.operation == "update"
    assert updated.affected_rows == 2

    deleted = hyper.execute_hyper_sql(
        str(dest), 'DELETE FROM "Extract"."Itens" WHERE id = 3'
    )
    assert isinstance(deleted, HyperMutationResult), deleted
    assert deleted.operation == "delete"
    assert deleted.affected_rows == 1

    report = hyper.inspect_hyper_schema(str(dest))
    assert isinstance(report, HyperSchemaReport), report
    assert report.tables[0].row_count == 2


# -- 91: extração de banco externo (SQLite local) → .hyper ---------------------


def test_extract_database_para_hyper_com_sqlite_local(
    tmp_path: Path, hyper_offline_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extrai de um SQLite real (via SQLAlchemy) e materializa o resultado."""
    db_path = tmp_path / "origem.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE clientes (id INTEGER, nome TEXT, receita REAL)")
        conn.executemany(
            "INSERT INTO clientes VALUES (?, ?, ?)",
            [(1, "Ana", 10.5), (2, "Bruno", 20.0)],
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("HYPER_DB_CONN_TESTE", f"sqlite:///{db_path}")
    dest = tmp_path / "extraido.hyper"

    result = hyper.extract_database_to_hyper(
        "TESTE", "SELECT id, nome, receita FROM clientes ORDER BY id", str(dest)
    )
    assert isinstance(result, HyperCreateResult), result
    assert result.source == "database"
    assert result.row_count == 2
    assert {col.name for col in result.columns} == {"id", "nome", "receita"}

    report = hyper.inspect_hyper_schema(str(dest))
    assert isinstance(report, HyperSchemaReport), report
    assert report.tables[0].row_count == 2


# -- 92: publicação do .hyper no Tableau real (requer credenciais) -------------


@pytest.mark.skipif(
    os.getenv("TABLEAU_INTEGRATION") != "1",
    reason="Defina TABLEAU_INTEGRATION=1 e as credenciais de sandbox para publicar.",
)
def test_publicacao_hyper_no_tableau_real(sample_hyper: Path) -> None:
    """Publica um `.hyper` mínimo como datasource — fecha o fluxo do PRD (RF21–RF22)."""
    project = os.getenv("TABLEAU_IT_PROJECT")
    if not project:
        pytest.skip("Variável de sandbox 'TABLEAU_IT_PROJECT' ausente.")

    published = deploy.publish_datasource(str(sample_hyper), project, overwrite=True)
    assert isinstance(published, PublishResult), getattr(published, "error", published)
    assert published.status == "success"
    assert published.content_type == "datasource"
    # O content_id é encadeável com metadados/QA (RF22).
    assert published.content_id

"""Testes unitários das tools de Hyper Datasources (`tools/hyper.py`).

O motor Hyper (`hyper_session`/`HyperEngine`) e a extração de banco (`hyper.db`)
são sempre mockados no limite da integração — sem runtime Hyper, sem rede e sem
banco real. A validação local (extensão/existência/parâmetros) deve ocorrer
**antes** de qualquer uso do engine.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_tableau.hyper.db import ExtractReport
from mcp_tableau.hyper.engine import (
    HyperEngineError,
    QueryRows,
    TableReport,
)
from mcp_tableau.models import (
    ErrorCode,
    HyperColumn,
    HyperCreateResult,
    HyperMutationResult,
    HyperQueryResult,
    HyperSchemaReport,
    InlineColumn,
    ToolError,
    VolumeAlert,
)
from mcp_tableau.tools import hyper


@pytest.fixture
def engine() -> MagicMock:
    """Mock do `HyperEngine` com os métodos consumidos pelas tools."""
    return MagicMock(name="HyperEngine")


@pytest.fixture
def session(engine: MagicMock, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Monkeypatcha `hyper_session` no módulo `hyper` para render o `engine` mock.

    Retorna o mock de `hyper_session` para asserts de "não abriu sessão".
    """
    session_cm = MagicMock(name="hyper_session")
    session_cm.return_value.__enter__.return_value = engine
    session_cm.return_value.__exit__.return_value = False
    monkeypatch.setattr(hyper, "hyper_session", session_cm)
    return session_cm


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Monkeypatcha `load_settings` com limiares previsíveis para a suite rápida."""
    fake = MagicMock(name="Settings")
    fake.hyper_max_result_rows = 200
    fake.hyper_max_source_file_mb = 500
    fake.hyper_max_inline_rows = 1_000
    fake.hyper_max_extract_rows = 5_000_000
    monkeypatch.setattr(hyper, "load_settings", MagicMock(return_value=fake))
    return fake


def _hyper_file(tmp_path: Path, name: str = "extrato") -> Path:
    """Cria um arquivo `.hyper` de exemplo (conteúdo irrelevante — motor mockado)."""
    path = tmp_path / f"{name}.hyper"
    path.write_bytes(b"\0" * 64)
    return path


def _csv_file(tmp_path: Path, name: str = "vendas") -> Path:
    """Cria um arquivo `.csv` de origem de exemplo."""
    path = tmp_path / f"{name}.csv"
    path.write_text("codigo,nome\n101,Campinas\n")
    return path


def _table_report(
    *, table_name: str = "Extract", row_count: int | None = 2
) -> TableReport:
    """`TableReport` de exemplo para o engine mock retornar."""
    return TableReport(
        schema_name="Extract",
        table_name=table_name,
        columns=[
            HyperColumn(name="codigo", type="big_int", nullable=False),
            HyperColumn(name="nome", type="text", nullable=True),
        ],
        row_count=row_count,
    )


# -- query_hyper ---------------------------------------------------------------


def test_query_hyper_sucesso_retorna_colunas_e_linhas(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    engine.query.return_value = QueryRows(
        columns=[
            HyperColumn(name="filial", type="text", nullable=True),
            HyperColumn(name="total", type="double", nullable=True),
        ],
        rows=[["Campinas", 1250341.55], ["Santos", 987222.10]],
        truncated=False,
    )

    result = hyper.query_hyper(str(path), 'SELECT * FROM "Extract"."Extract"')

    assert isinstance(result, HyperQueryResult)
    assert result.status == "success"
    assert [c.name for c in result.columns] == ["filial", "total"]
    assert result.rows == [["Campinas", 1250341.55], ["Santos", 987222.10]]
    assert result.row_count == 2
    assert result.truncated is False
    assert result.max_rows == 200
    engine.query.assert_called_once_with(path, 'SELECT * FROM "Extract"."Extract"', 200)


def test_query_hyper_resultado_vazio_e_sucesso(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    engine.query.return_value = QueryRows(columns=[], rows=[], truncated=False)

    result = hyper.query_hyper(str(path), "SELECT 1 WHERE 1 = 0")

    assert isinstance(result, HyperQueryResult)
    assert result.rows == []
    assert result.row_count == 0
    assert result.truncated is False


def test_query_hyper_comando_de_escrita_retorna_validation_error_orientando_execute_hyper_sql(  # noqa: E501
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)

    result = hyper.query_hyper(str(path), "DELETE FROM Extract.Extract")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    assert "execute_hyper_sql" in result.error.message
    session.assert_not_called()
    engine.query.assert_not_called()


def test_query_hyper_max_rows_default_vem_de_settings(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    settings.hyper_max_result_rows = 42
    engine.query.return_value = QueryRows(columns=[], rows=[], truncated=False)

    result = hyper.query_hyper(str(path), "SELECT 1")

    assert isinstance(result, HyperQueryResult)
    assert result.max_rows == 42
    engine.query.assert_called_once_with(path, "SELECT 1", 42)


def test_query_hyper_max_rows_fora_do_intervalo_retorna_validation_error(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)

    result = hyper.query_hyper(str(path), "SELECT 1", max_rows=0)

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    session.assert_not_called()

    result_alto = hyper.query_hyper(str(path), "SELECT 1", max_rows=10_001)
    assert isinstance(result_alto, ToolError)
    assert result_alto.error.code is ErrorCode.VALIDATION_ERROR


def test_query_hyper_sql_invalido_retorna_hyper_sql_error_com_mensagem_do_motor(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    engine.query.side_effect = HyperEngineError(
        ErrorCode.HYPER_SQL_ERROR, 'column "inexistente" does not exist'
    )

    result = hyper.query_hyper(str(path), "SELECT inexistente FROM t")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.HYPER_SQL_ERROR
    assert "inexistente" in result.error.message


def test_query_hyper_arquivo_invalido_retorna_hyper_invalid_file(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    csv_path = tmp_path / "vendas.csv"
    csv_path.write_text("a,b\n1,2\n")

    result = hyper.query_hyper(str(csv_path), "SELECT 1")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.HYPER_INVALID_FILE
    session.assert_not_called()


# -- inspect_hyper_schema ------------------------------------------------------


def test_inspect_hyper_schema_sucesso_retorna_relatorio_completo(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    engine.describe.return_value = [
        TableReport(
            schema_name="Extract",
            table_name="Extract",
            columns=[
                HyperColumn(name="data_venda", type="date", nullable=True),
                HyperColumn(name="valor_venda", type="double", nullable=True),
            ],
            row_count=184230,
        ),
        TableReport(
            schema_name="Extract",
            table_name="corrompida",
            columns=[],
            row_count=None,
        ),
    ]

    result = hyper.inspect_hyper_schema(str(path))

    assert isinstance(result, HyperSchemaReport)
    assert result.status == "success"
    assert result.hyper_path == str(path)
    assert result.file_size_bytes == 64
    assert len(result.tables) == 2
    assert result.tables[0].table_name == "Extract"
    assert result.tables[0].row_count == 184230
    assert result.tables[1].row_count is None
    engine.describe.assert_called_once_with(path)


def test_inspect_hyper_schema_arquivo_invalido_retorna_hyper_invalid_file(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    csv_path = tmp_path / "vendas.csv"
    csv_path.write_text("a,b\n1,2\n")

    result = hyper.inspect_hyper_schema(str(csv_path))

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.HYPER_INVALID_FILE
    session.assert_not_called()
    engine.describe.assert_not_called()


# -- create_hyper_from_file ----------------------------------------------------


def test_create_hyper_from_file_sucesso_retorna_hyper_create_result(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    source = _csv_file(tmp_path)
    dest = tmp_path / "extrato.hyper"
    engine.create_table_from_file.return_value = _table_report(row_count=3)

    result = hyper.create_hyper_from_file(str(source), str(dest), delimiter=";")

    assert isinstance(result, HyperCreateResult)
    assert result.status == "success"
    assert result.source == "csv"
    assert result.row_count == 3
    assert result.hyper_path == str(dest)
    assert result.warnings == []
    request = engine.create_table_from_file.call_args.args[0]
    assert request.source_path == source
    assert request.source_format == "csv"
    assert request.delimiter == ";"


def test_create_hyper_from_file_origem_inexistente_retorna_invalid_file(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    dest = tmp_path / "extrato.hyper"

    result = hyper.create_hyper_from_file(str(tmp_path / "ausente.csv"), str(dest))

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.INVALID_FILE
    session.assert_not_called()
    engine.create_table_from_file.assert_not_called()


def test_create_hyper_from_file_extensao_desconhecida_sem_format_retorna_invalid_file(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    source = tmp_path / "dados.txt"
    source.write_text("qualquer coisa")
    dest = tmp_path / "extrato.hyper"

    result = hyper.create_hyper_from_file(str(source), str(dest))

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.INVALID_FILE
    session.assert_not_called()


def test_create_hyper_from_file_acima_do_limiar_sem_confirmacao_retorna_volume_alert(
    tmp_path: Path, engine: MagicMock, session: MagicMock, hyper_env: dict[str, str]
) -> None:
    source = _csv_file(tmp_path)
    dest = tmp_path / "extrato.hyper"

    result = hyper.create_hyper_from_file(str(source), str(dest))

    assert isinstance(result, VolumeAlert)
    assert result.status == "volume_alert"
    assert result.exceeded[0].dimension == "source_file_mb"
    session.assert_not_called()
    engine.create_table_from_file.assert_not_called()


def test_create_hyper_from_file_acima_do_limiar_com_confirmacao_executa_e_adiciona_warning(  # noqa: E501
    tmp_path: Path, engine: MagicMock, session: MagicMock, hyper_env: dict[str, str]
) -> None:
    source = _csv_file(tmp_path)
    dest = tmp_path / "extrato.hyper"
    engine.create_table_from_file.return_value = _table_report(row_count=1)

    result = hyper.create_hyper_from_file(
        str(source), str(dest), confirm_large_operation=True
    )

    assert isinstance(result, HyperCreateResult)
    assert len(result.warnings) == 1
    assert "source_file_mb" in result.warnings[0]
    engine.create_table_from_file.assert_called_once()


def test_create_hyper_from_file_valida_antes_de_abrir_hyper_session(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    source = _csv_file(tmp_path)
    dest = tmp_path / "extrato.txt"  # extensão de destino inválida

    result = hyper.create_hyper_from_file(str(source), str(dest))

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    session.assert_not_called()
    engine.create_table_from_file.assert_not_called()


# -- create_hyper_from_inline --------------------------------------------------


def _inline_columns() -> list[InlineColumn]:
    """Colunas inline de exemplo (codigo big_int não nulo, nome text)."""
    return [
        InlineColumn(name="codigo", type="big_int", nullable=False),
        InlineColumn(name="nome", type="text"),
    ]


def test_create_hyper_from_inline_sucesso_retorna_source_inline(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    dest = tmp_path / "depara.hyper"
    engine.create_table_from_rows.return_value = _table_report(
        table_name="depara", row_count=2
    )

    result = hyper.create_hyper_from_inline(
        str(dest),
        "depara",
        _inline_columns(),
        [[101, "Campinas"], [102, "Santos"]],
    )

    assert isinstance(result, HyperCreateResult)
    assert result.source == "inline"
    assert result.row_count == 2
    request = engine.create_table_from_rows.call_args.args[0]
    assert request.rows == [[101, "Campinas"], [102, "Santos"]]


def test_create_hyper_from_inline_linha_com_aridade_errada_retorna_schema_mismatch_com_indice(  # noqa: E501
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    dest = tmp_path / "depara.hyper"

    result = hyper.create_hyper_from_inline(
        str(dest),
        "depara",
        _inline_columns(),
        [[101, "Campinas"], [102]],  # segunda linha sem a coluna nome
    )

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.HYPER_SCHEMA_MISMATCH
    assert "Linha 2" in result.error.message
    session.assert_not_called()
    engine.create_table_from_rows.assert_not_called()


def test_create_hyper_from_inline_valor_nao_coercivel_retorna_schema_mismatch(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    dest = tmp_path / "depara.hyper"

    result = hyper.create_hyper_from_inline(
        str(dest),
        "depara",
        _inline_columns(),
        [["abc", "Campinas"]],  # 'abc' não é big_int
    )

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.HYPER_SCHEMA_MISMATCH
    assert "codigo" in result.error.message
    session.assert_not_called()


def test_create_hyper_from_inline_colunas_duplicadas_retorna_validation_error(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    dest = tmp_path / "depara.hyper"
    columns = [
        InlineColumn(name="codigo", type="big_int"),
        InlineColumn(name="codigo", type="text"),
    ]

    result = hyper.create_hyper_from_inline(str(dest), "depara", columns, [[1, "x"]])

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    session.assert_not_called()


def test_create_hyper_from_inline_acima_do_limiar_sem_confirmacao_retorna_volume_alert(
    tmp_path: Path, engine: MagicMock, session: MagicMock, hyper_env: dict[str, str]
) -> None:
    dest = tmp_path / "depara.hyper"
    rows = [[101, "A"], [102, "B"], [103, "C"]]  # 3 > HYPER_MAX_INLINE_ROWS=2

    result = hyper.create_hyper_from_inline(
        str(dest), "depara", _inline_columns(), rows
    )

    assert isinstance(result, VolumeAlert)
    assert result.exceeded[0].dimension == "inline_rows"
    session.assert_not_called()
    engine.create_table_from_rows.assert_not_called()


# -- append_to_hyper -----------------------------------------------------------


def test_append_to_hyper_inline_sucesso_retorna_affected_rows(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    engine.append_rows.return_value = 1

    result = hyper.append_to_hyper(
        str(path),
        "depara",
        columns=_inline_columns(),
        rows=[[103, "Sorocaba"]],
    )

    assert isinstance(result, HyperMutationResult)
    assert result.operation == "append"
    assert result.affected_rows == 1
    assert result.table_name == "depara"
    request = engine.append_rows.call_args.args[0]
    assert request.rows == [[103, "Sorocaba"]]


def test_append_to_hyper_de_arquivo_sucesso(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    source = _csv_file(tmp_path)
    engine.execute.return_value = 5

    result = hyper.append_to_hyper(str(path), "Extract", source_path=str(source))

    assert isinstance(result, HyperMutationResult)
    assert result.operation == "append"
    assert result.affected_rows == 5
    engine.execute.assert_called_once()
    sql = engine.execute.call_args.args[1]
    assert sql.startswith("INSERT INTO")
    assert "external(" in sql


def test_append_to_hyper_sem_origem_retorna_validation_error(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)

    result = hyper.append_to_hyper(str(path), "Extract")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    session.assert_not_called()


def test_append_to_hyper_com_duas_origens_retorna_validation_error(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    source = _csv_file(tmp_path)

    result = hyper.append_to_hyper(
        str(path),
        "Extract",
        source_path=str(source),
        columns=_inline_columns(),
        rows=[[1, "x"]],
    )

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    session.assert_not_called()


def test_append_to_hyper_tabela_inexistente_retorna_not_found(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    engine.append_rows.side_effect = HyperEngineError(
        ErrorCode.HYPER_SQL_ERROR, 'table "Extract"."depara" does not exist'
    )

    result = hyper.append_to_hyper(
        str(path), "depara", columns=_inline_columns(), rows=[[1, "x"]]
    )

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.NOT_FOUND


# -- execute_hyper_sql ---------------------------------------------------------


def test_execute_hyper_sql_update_retorna_linhas_afetadas(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    engine.execute.return_value = 5

    result = hyper.execute_hyper_sql(
        str(path), 'UPDATE "Extract"."Extract" SET valor = 0 WHERE valor IS NULL'
    )

    assert isinstance(result, HyperMutationResult)
    assert result.operation == "update"
    assert result.affected_rows == 5
    assert result.table_name == "Extract"


def test_execute_hyper_sql_create_table_as_retorna_operation_create_table_as(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)
    engine.execute.return_value = 14

    result = hyper.execute_hyper_sql(
        str(path),
        'CREATE TABLE "Extract"."vendas_por_filial" AS '
        'SELECT filial, SUM(valor) AS total FROM "Extract"."Extract" '
        "GROUP BY filial",
    )

    assert isinstance(result, HyperMutationResult)
    assert result.operation == "create_table_as"
    assert result.affected_rows == 14
    assert result.table_name == "vendas_por_filial"


def test_execute_hyper_sql_select_retorna_validation_error_orientando_query_hyper(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)

    result = hyper.execute_hyper_sql(str(path), "SELECT * FROM Extract.Extract")

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    assert "query_hyper" in result.error.message
    session.assert_not_called()
    engine.execute.assert_not_called()


def test_execute_hyper_sql_palavra_chave_drop_retorna_validation_error(
    tmp_path: Path, engine: MagicMock, session: MagicMock, settings: MagicMock
) -> None:
    path = _hyper_file(tmp_path)

    result = hyper.execute_hyper_sql(str(path), 'DROP TABLE "Extract"."Extract"')

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    session.assert_not_called()
    engine.execute.assert_not_called()


# -- extract_database_to_hyper -------------------------------------------------


def _extract_report(
    *, row_count: int = 2, warnings: list[str] | None = None
) -> ExtractReport:
    """`ExtractReport` de exemplo para o `db.extract_to_hyper` mock retornar."""
    return ExtractReport(
        columns=[
            HyperColumn(name="filial", type="text", nullable=True),
            HyperColumn(name="valor", type="double", nullable=True),
        ],
        row_count=row_count,
        warnings=list(warnings or []),
    )


@pytest.fixture
def extract(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Monkeypatcha `db.extract_to_hyper` no módulo `hyper` (sem banco/runtime)."""
    fake = MagicMock(name="extract_to_hyper", return_value=_extract_report())
    monkeypatch.setattr(hyper.db, "extract_to_hyper", fake)
    return fake


def test_extract_database_to_hyper_sucesso_retorna_source_database(
    tmp_path: Path, extract: MagicMock, settings: MagicMock
) -> None:
    dest = tmp_path / "vendas_dw.hyper"

    result = hyper.extract_database_to_hyper(
        "VENDAS", "SELECT filial, valor FROM fato", str(dest)
    )

    assert isinstance(result, HyperCreateResult)
    assert result.source == "database"
    assert result.row_count == 2
    assert result.table_name == "Extract"
    assert result.warnings == []
    extract.assert_called_once_with(
        "VENDAS", "SELECT filial, valor FROM fato", dest, "Extract"
    )


def test_extract_database_to_hyper_connection_name_com_url_retorna_validation_error(
    tmp_path: Path, extract: MagicMock, settings: MagicMock
) -> None:
    dest = tmp_path / "vendas_dw.hyper"

    result = hyper.extract_database_to_hyper(
        "postgresql://user:pass@host/db", "SELECT 1", str(dest)
    )

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    extract.assert_not_called()


def test_extract_database_to_hyper_conexao_nao_configurada_retorna_erro_com_nome_da_variavel(  # noqa: E501
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, settings: MagicMock
) -> None:
    dest = tmp_path / "vendas_dw.hyper"

    def _raise(*args: object, **kwargs: object) -> None:
        raise hyper.db.DbConfigError(
            ErrorCode.DB_CONNECTION_NOT_CONFIGURED,
            "Conexão 'FINANCEIRO' não configurada. Defina a variável de "
            "ambiente HYPER_DB_CONN_FINANCEIRO no host do servidor MCP.",
        )

    monkeypatch.setattr(hyper.db, "extract_to_hyper", _raise)

    result = hyper.extract_database_to_hyper("FINANCEIRO", "SELECT 1", str(dest))

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.DB_CONNECTION_NOT_CONFIGURED
    assert "HYPER_DB_CONN_FINANCEIRO" in result.error.message


def test_extract_database_to_hyper_linhas_acima_do_limiar_conclui_com_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hyper_env: dict[str, str]
) -> None:
    dest = tmp_path / "vendas_dw.hyper"
    # HYPER_MAX_EXTRACT_ROWS=5 no hyper_env; 10 linhas excedem o limiar.
    fake = MagicMock(return_value=_extract_report(row_count=10))
    monkeypatch.setattr(hyper.db, "extract_to_hyper", fake)

    result = hyper.extract_database_to_hyper("VENDAS", "SELECT * FROM fato", str(dest))

    assert isinstance(result, HyperCreateResult)
    assert result.row_count == 10
    assert len(result.warnings) == 1
    assert "extracted_rows" in result.warnings[0]


def test_extract_database_to_hyper_destino_invalido_retorna_validation_error(
    tmp_path: Path, extract: MagicMock, settings: MagicMock
) -> None:
    dest = tmp_path / "vendas_dw.txt"  # extensão de destino inválida

    result = hyper.extract_database_to_hyper("VENDAS", "SELECT 1", str(dest))

    assert isinstance(result, ToolError)
    assert result.error.code is ErrorCode.VALIDATION_ERROR
    extract.assert_not_called()


def test_nenhum_retorno_ou_log_contem_connection_string(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    settings: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Caso 78: nem o retorno nem os logs podem conter a connection string."""
    dest = tmp_path / "vendas_dw.hyper"
    url = "postgresql+psycopg://vendas_user:s3nh4-secreta@db.interno:5432/dw"
    url_parts = ("vendas_user", "s3nh4-secreta", "db.interno", url)

    # A tool jamais recebe/repassa a URL: o db mock devolve um relatório limpo.
    warning_livre = "Coluna 'x': tipo de origem não mapeado; convertido para text."
    fake = MagicMock(return_value=_extract_report(warnings=[warning_livre]))
    monkeypatch.setattr(hyper.db, "extract_to_hyper", fake)

    with caplog.at_level(logging.DEBUG):
        result = hyper.extract_database_to_hyper("VENDAS", "SELECT 1", str(dest))

    assert isinstance(result, HyperCreateResult)
    payload = result.model_dump_json()
    for part in url_parts:
        assert part not in payload
        assert part not in caplog.text

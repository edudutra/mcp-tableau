"""Testes unitários do `HyperEngine` com `tableauhyperapi` inteiramente mockada.

O runtime Hyper não está instalado na suíte rápida/CI; estes testes injetam um
módulo falso (`FakeHapi`) em `engine.hapi` e exercitam o comportamento do engine
sem tocar no motor real. Cobrem os casos 18–34 da techspec.
"""

from __future__ import annotations

import datetime
import types
from decimal import Decimal
from pathlib import Path

import pytest

from mcp_tableau.hyper import engine
from mcp_tableau.models import ErrorCode, InlineColumn

# -- Duplos de teste da tableauhyperapi ---------------------------------------

_NULLABLE = object()
_NOT_NULLABLE = object()


class FakeHyperException(Exception):
    """Substituto de `tableauhyperapi.HyperException` com `main_message`."""

    def __init__(self, main_message: str) -> None:
        super().__init__(main_message)
        self.main_message = main_message


class FakeTypeTag:
    """Tag de tipo com `.name`, análoga ao `TypeTag` do Hyper."""

    def __init__(self, name: str) -> None:
        self.name = name


_TAGS: dict[str, FakeTypeTag] = {}


def _tag(name: str) -> FakeTypeTag:
    return _TAGS.setdefault(name, FakeTypeTag(name))


class FakeSqlType:
    """Substituto de `SqlType`: expõe `.tag` e opcionalmente precisão/escala."""

    def __init__(self, tag_name: str, precision=None, scale=None) -> None:
        self.tag = _tag(tag_name)
        self.precision = precision
        self.scale = scale


class FakeSqlTypeFactory:
    """Fábrica estática espelhando `SqlType.text()`, `SqlType.numeric(p, s)`, etc."""

    text = staticmethod(lambda: FakeSqlType("TEXT"))
    big_int = staticmethod(lambda: FakeSqlType("BIG_INT"))
    double = staticmethod(lambda: FakeSqlType("DOUBLE"))
    bool = staticmethod(lambda: FakeSqlType("BOOL"))
    date = staticmethod(lambda: FakeSqlType("DATE"))
    timestamp = staticmethod(lambda: FakeSqlType("TIMESTAMP"))
    timestamp_tz = staticmethod(lambda: FakeSqlType("TIMESTAMP_TZ"))
    numeric = staticmethod(lambda p, s: FakeSqlType("NUMERIC", p, s))


class FakeColumn:
    """Coluna de `TableDefinition`/resultado com nome, tipo e nulabilidade."""

    def __init__(self, name: str, type: FakeSqlType, nullability=_NULLABLE) -> None:
        self.name = name
        self.type = type
        self.nullability = nullability


class FakeTableDefinition:
    """Substituto de `TableDefinition` com o `Column` aninhado."""

    Column = FakeColumn

    def __init__(self, table_name: object, columns: list[FakeColumn]) -> None:
        self.table_name = table_name
        self.columns = columns


class FakeTableName:
    """Nome qualificado: `str` vira `"schema"."tabela"`; guarda o `name` folha."""

    def __init__(self, *parts: str) -> None:
        self.parts = parts
        self.name = parts[-1]

    def __str__(self) -> str:
        return ".".join(f'"{part}"' for part in self.parts)


class FakeSchemaName:
    def __init__(self, name: str) -> None:
        self.name = name

    def __str__(self) -> str:
        return f'"{self.name}"'


def _escape_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class FakeQueryResult:
    """Resultado de `execute_query`: context manager, iterável e com `.schema`."""

    def __init__(self, rows: list[list[object]], columns: list[FakeColumn]) -> None:
        self._rows = rows
        self.schema = types.SimpleNamespace(columns=columns)

    def __enter__(self) -> FakeQueryResult:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def __iter__(self):
        return iter(self._rows)


class FakeInserter:
    """Substituto de `Inserter`: acumula linhas e registra `execute()`."""

    def __init__(self, connection: object, definition: object) -> None:
        self.connection = connection
        self.definition = definition
        self.added: list[object] = []
        self.executed = False

    def __enter__(self) -> FakeInserter:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def add_rows(self, rows) -> None:
        self.added.extend(rows)

    def execute(self) -> None:
        self.executed = True


class FakeCatalog:
    """Catálogo configurável: schemas, tabelas, definições e criações."""

    def __init__(self) -> None:
        self.created_schemas: list[object] = []
        self.created_tables: list[object] = []
        self.table_definitions: dict[str, FakeTableDefinition] = {}
        self.schema_names: list[object] = []
        self.table_names: dict[str, list[object]] = {}
        self.get_definition_calls: list[object] = []

    def create_schema_if_not_exists(self, schema: object) -> None:
        self.created_schemas.append(schema)

    def create_table(self, definition: object) -> None:
        self.created_tables.append(definition)

    def get_table_definition(self, table: object) -> FakeTableDefinition:
        self.get_definition_calls.append(table)
        return self.table_definitions[str(table)]

    def get_schema_names(self) -> list[object]:
        return self.schema_names

    def get_table_names(self, schema: object) -> list[object]:
        return self.table_names.get(str(schema), [])


class FakeConnection:
    """Conexão configurável: registra comandos e devolve resultados fixados."""

    def __init__(self) -> None:
        self.catalog = FakeCatalog()
        self.commands: list[str] = []
        self.command_return: int | None = 0
        self.command_error: Exception | None = None
        self.query_rows: list[list[object]] = []
        self.query_columns: list[FakeColumn] = []
        self.last_query: str | None = None
        self.scalar_return: int | None = 0
        self.scalar_error: Exception | None = None

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute_command(self, command: str) -> int | None:
        self.commands.append(command)
        if self.command_error is not None:
            raise self.command_error
        return self.command_return

    def execute_query(self, query: str) -> FakeQueryResult:
        self.last_query = query
        return FakeQueryResult(self.query_rows, self.query_columns)

    def execute_scalar_query(self, query: str) -> int | None:
        if self.scalar_error is not None:
            raise self.scalar_error
        return self.scalar_return


class FakeHyperProcess:
    """Processo Hyper falso: context manager que registra entrada/saída."""

    def __init__(self, telemetry: object = None) -> None:
        self.telemetry = telemetry
        self.endpoint = "endpoint://fake"
        self.entered = False
        self.exited = False

    def __enter__(self) -> FakeHyperProcess:
        self.entered = True
        return self

    def __exit__(self, *exc: object) -> bool:
        self.exited = True
        return False


class FakeHapi:
    """Fachada que imita o módulo `tableauhyperapi` usado pelo engine."""

    HyperException = FakeHyperException
    SqlType = FakeSqlTypeFactory
    TableDefinition = FakeTableDefinition
    TableName = FakeTableName
    SchemaName = FakeSchemaName
    NULLABLE = _NULLABLE
    NOT_NULLABLE = _NOT_NULLABLE
    escape_string_literal = staticmethod(_escape_string_literal)

    Telemetry = types.SimpleNamespace(
        DO_NOT_SEND_USAGE_DATA_TO_TABLEAU="DO_NOT_SEND",
        SEND_USAGE_DATA_TO_TABLEAU="SEND",
    )
    CreateMode = types.SimpleNamespace(
        CREATE_AND_REPLACE="CREATE_AND_REPLACE",
        CREATE_IF_NOT_EXISTS="CREATE_IF_NOT_EXISTS",
        NONE="NONE",
    )

    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.process = FakeHyperProcess()
        self.inserters: list[FakeInserter] = []
        self.connection_calls: list[dict[str, object]] = []

    def HyperProcess(self, telemetry: object = None) -> FakeHyperProcess:
        self.process.telemetry = telemetry
        return self.process

    def Connection(
        self,
        endpoint: object = None,
        database: object = None,
        create_mode: object = None,
    ) -> FakeConnection:
        self.connection_calls.append(
            {"endpoint": endpoint, "database": database, "create_mode": create_mode}
        )
        return self.connection

    def Inserter(self, connection: object, definition: object) -> FakeInserter:
        inserter = FakeInserter(connection, definition)
        self.inserters.append(inserter)
        return inserter


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeHapi:
    """Injeta o `tableauhyperapi` falso em `engine.hapi`."""
    fake_module = FakeHapi()
    monkeypatch.setattr(engine, "hapi", fake_module)
    return fake_module


def _qualified(table: str) -> str:
    """Chave do catálogo para a tabela no schema `Extract`."""
    return str(FakeTableName(engine.EXTRACT_SCHEMA, table))


# -- 18–19: ciclo de vida da sessão --------------------------------------------


def test_hyper_session_inicia_processo_com_telemetria_desativada(
    fake: FakeHapi,
) -> None:
    with engine.hyper_session() as eng:
        assert isinstance(eng, engine.HyperEngine)

    assert fake.process.telemetry == fake.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU
    assert fake.process.entered is True
    assert fake.process.exited is True


def test_hyper_session_encerra_processo_mesmo_com_excecao(fake: FakeHapi) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with engine.hyper_session():
            raise RuntimeError("boom")

    assert fake.process.exited is True


def test_hyper_session_sem_runtime_levanta_erro_acionavel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(engine, "hapi", None)
    with pytest.raises(engine.HyperEngineError) as exc_info:
        with engine.hyper_session():
            pass
    assert exc_info.value.code == ErrorCode.HYPER_SQL_ERROR


# -- 20–23: criação a partir de arquivo ----------------------------------------


def test_create_table_from_file_csv_com_schema_usa_copy_com_delimitador_e_encoding(
    fake: FakeHapi,
) -> None:
    fake.connection.command_return = 42
    fake.connection.catalog.table_definitions[_qualified("Vendas")] = (
        FakeTableDefinition(
            FakeTableName(engine.EXTRACT_SCHEMA, "Vendas"),
            [FakeColumn("filial", FakeSqlType("TEXT"))],
        )
    )
    req = engine.FileIngestRequest(
        source_path=Path("/data/vendas.csv"),
        hyper_path=Path("/out/vendas.hyper"),
        table_name="Vendas",
        source_format="csv",
        delimiter=";",
        encoding="latin-1",
        header=True,
        schema=[InlineColumn(name="filial", type="text")],
    )

    with engine.hyper_session() as eng:
        report = eng.create_table_from_file(req)

    command = fake.connection.commands[0]
    assert command.startswith("COPY")
    assert "format => 'csv'" in command
    assert "delimiter => ';'" in command
    assert "encoding => 'latin-1'" in command
    assert "header => true" in command
    assert report.row_count == 42
    assert report.table_name == "Vendas"


def test_create_table_from_file_csv_sem_schema_usa_external_para_inferencia(
    fake: FakeHapi,
) -> None:
    fake.connection.command_return = 10
    fake.connection.catalog.table_definitions[_qualified("Extract")] = (
        FakeTableDefinition(
            FakeTableName(engine.EXTRACT_SCHEMA, "Extract"),
            [FakeColumn("a", FakeSqlType("BIG_INT"))],
        )
    )
    req = engine.FileIngestRequest(
        source_path=Path("/data/dados.csv"),
        hyper_path=Path("/out/dados.hyper"),
        table_name="Extract",
        source_format="csv",
        schema=None,
    )

    with engine.hyper_session() as eng:
        eng.create_table_from_file(req)

    command = fake.connection.commands[0]
    assert command.startswith("CREATE TABLE")
    assert "external(" in command
    assert "format => 'csv'" in command


def test_create_table_from_file_parquet_usa_external(fake: FakeHapi) -> None:
    fake.connection.command_return = 99
    fake.connection.catalog.table_definitions[_qualified("Extract")] = (
        FakeTableDefinition(
            FakeTableName(engine.EXTRACT_SCHEMA, "Extract"),
            [FakeColumn("a", FakeSqlType("DOUBLE"))],
        )
    )
    req = engine.FileIngestRequest(
        source_path=Path("/data/dados.parquet"),
        hyper_path=Path("/out/dados.hyper"),
        source_format="parquet",
        schema=None,
    )

    with engine.hyper_session() as eng:
        eng.create_table_from_file(req)

    command = fake.connection.commands[0]
    assert "external(" in command
    assert "format => 'csv'" not in command


def test_create_table_from_file_escapa_path_com_escape_string_literal(
    fake: FakeHapi,
) -> None:
    fake.connection.command_return = 1
    fake.connection.catalog.table_definitions[_qualified("Extract")] = (
        FakeTableDefinition(
            FakeTableName(engine.EXTRACT_SCHEMA, "Extract"),
            [FakeColumn("a", FakeSqlType("TEXT"))],
        )
    )
    req = engine.FileIngestRequest(
        source_path=Path("/data/o'brien.parquet"),
        hyper_path=Path("/out/x.hyper"),
        source_format="parquet",
        schema=None,
    )

    with engine.hyper_session() as eng:
        eng.create_table_from_file(req)

    command = fake.connection.commands[0]
    # A aspa simples do path é duplicada pelo escape_string_literal.
    assert "'/data/o''brien.parquet'" in command


# -- 24: criação inline --------------------------------------------------------


def test_create_table_from_rows_insere_via_inserter_e_retorna_contagem(
    fake: FakeHapi,
) -> None:
    req = engine.InlineIngestRequest(
        hyper_path=Path("/out/inline.hyper"),
        table_name="T",
        columns=[InlineColumn(name="id", type="big_int", nullable=False)],
        rows=[[1], [2], [3]],
    )

    with engine.hyper_session() as eng:
        report = eng.create_table_from_rows(req)

    assert fake.inserters[0].executed is True
    assert fake.inserters[0].added == [[1], [2], [3]]
    assert report.row_count == 3
    assert report.columns[0].name == "id"
    assert report.columns[0].type == "big_int"


def test_create_table_from_rows_com_numeric_mapeia_precisao_e_escala(
    fake: FakeHapi,
) -> None:
    req = engine.InlineIngestRequest(
        hyper_path=Path("/out/inline.hyper"),
        table_name="T",
        columns=[InlineColumn(name="valor", type="numeric(10,2)")],
        rows=[[Decimal("1.50")]],
    )

    with engine.hyper_session() as eng:
        report = eng.create_table_from_rows(req)

    # A definição criada usa SqlType.numeric(10, 2) (tag NUMERIC).
    created = fake.connection.catalog.created_tables[0]
    assert created.columns[0].type.tag.name == "NUMERIC"
    assert created.columns[0].type.precision == 10
    assert created.columns[0].type.scale == 2
    assert report.columns[0].type == "numeric(10,2)"


def test_create_table_from_rows_if_not_exists_usa_create_mode_correto(
    fake: FakeHapi,
) -> None:
    req = engine.InlineIngestRequest(
        hyper_path=Path("/out/inline.hyper"),
        table_name="T",
        columns=[InlineColumn(name="id", type="big_int")],
        rows=[[1]],
        create_mode="if_not_exists",
    )

    with engine.hyper_session() as eng:
        eng.create_table_from_rows(req)

    assert (
        fake.connection_calls[0]["create_mode"] == fake.CreateMode.CREATE_IF_NOT_EXISTS
    )


# -- 25–26: append -------------------------------------------------------------


def test_append_rows_valida_compatibilidade_antes_de_inserir(fake: FakeHapi) -> None:
    existing = FakeTableDefinition(
        FakeTableName(engine.EXTRACT_SCHEMA, "T"),
        [FakeColumn("id", FakeSqlType("BIG_INT"))],
    )
    fake.connection.catalog.table_definitions[_qualified("T")] = existing
    req = engine.AppendRequest(
        hyper_path=Path("/out/t.hyper"),
        table_name="T",
        columns=[InlineColumn(name="id", type="big_int")],
        rows=[[9]],
    )

    with engine.hyper_session() as eng:
        affected = eng.append_rows(req)

    assert fake.connection.catalog.get_definition_calls  # validou o schema
    assert fake.inserters[0].definition is existing  # inseriu na tabela existente
    assert fake.inserters[0].executed is True
    assert affected == 1


def test_append_rows_schema_incompativel_levanta_hyper_schema_mismatch(
    fake: FakeHapi,
) -> None:
    existing = FakeTableDefinition(
        FakeTableName(engine.EXTRACT_SCHEMA, "T"),
        [
            FakeColumn("id", FakeSqlType("BIG_INT")),
            FakeColumn("nome", FakeSqlType("TEXT")),
        ],
    )
    fake.connection.catalog.table_definitions[_qualified("T")] = existing
    req = engine.AppendRequest(
        hyper_path=Path("/out/t.hyper"),
        table_name="T",
        columns=[InlineColumn(name="id", type="big_int")],  # falta uma coluna
        rows=[[9]],
    )

    with engine.hyper_session() as eng:
        with pytest.raises(engine.HyperEngineError) as exc_info:
            eng.append_rows(req)

    assert exc_info.value.code == ErrorCode.HYPER_SCHEMA_MISMATCH
    assert fake.inserters == []  # nada foi inserido


def test_append_rows_tipo_de_coluna_incompativel_levanta_schema_mismatch(
    fake: FakeHapi,
) -> None:
    existing = FakeTableDefinition(
        FakeTableName(engine.EXTRACT_SCHEMA, "T"),
        [FakeColumn("id", FakeSqlType("BIG_INT"))],
    )
    fake.connection.catalog.table_definitions[_qualified("T")] = existing
    req = engine.AppendRequest(
        hyper_path=Path("/out/t.hyper"),
        table_name="T",
        columns=[InlineColumn(name="id", type="text")],  # tipo divergente
        rows=[["x"]],
    )

    with engine.hyper_session() as eng:
        with pytest.raises(engine.HyperEngineError) as exc_info:
            eng.append_rows(req)

    assert exc_info.value.code == ErrorCode.HYPER_SCHEMA_MISMATCH
    assert fake.inserters == []


# -- 27–29: consulta -----------------------------------------------------------


def test_query_le_max_rows_mais_um_e_sinaliza_truncamento(fake: FakeHapi) -> None:
    fake.connection.query_columns = [FakeColumn("n", FakeSqlType("BIG_INT"))]
    fake.connection.query_rows = [[1], [2], [3], [4], [5]]

    with engine.hyper_session() as eng:
        result = eng.query(Path("/f.hyper"), "SELECT n FROM t", max_rows=3)

    assert result.truncated is True
    assert result.rows == [[1], [2], [3]]


def test_query_sem_excesso_nao_marca_truncamento(fake: FakeHapi) -> None:
    fake.connection.query_columns = [FakeColumn("n", FakeSqlType("BIG_INT"))]
    fake.connection.query_rows = [[1], [2]]

    with engine.hyper_session() as eng:
        result = eng.query(Path("/f.hyper"), "SELECT n FROM t", max_rows=3)

    assert result.truncated is False
    assert result.rows == [[1], [2]]


def test_query_serializa_date_e_timestamp_como_iso8601(fake: FakeHapi) -> None:
    fake.connection.query_columns = [
        FakeColumn("d", FakeSqlType("DATE")),
        FakeColumn("ts", FakeSqlType("TIMESTAMP")),
    ]
    fake.connection.query_rows = [
        [datetime.date(2026, 7, 2), datetime.datetime(2026, 7, 2, 10, 30, 15)]
    ]

    with engine.hyper_session() as eng:
        result = eng.query(Path("/f.hyper"), "SELECT * FROM t", max_rows=10)

    assert result.rows[0][0] == "2026-07-02"
    assert result.rows[0][1] == "2026-07-02T10:30:15"
    assert result.columns[0].type == "date"
    assert result.columns[1].type == "timestamp"


def test_query_serializa_numeric_como_string(fake: FakeHapi) -> None:
    fake.connection.query_columns = [FakeColumn("v", FakeSqlType("NUMERIC", 10, 4))]
    fake.connection.query_rows = [[Decimal("123.4500")]]

    with engine.hyper_session() as eng:
        result = eng.query(Path("/f.hyper"), "SELECT v FROM t", max_rows=10)

    assert result.rows[0][0] == "123.4500"
    assert isinstance(result.rows[0][0], str)
    assert result.columns[0].type == "numeric"


# -- 30: execução --------------------------------------------------------------


def test_execute_retorna_linhas_afetadas(fake: FakeHapi) -> None:
    fake.connection.command_return = 7

    with engine.hyper_session() as eng:
        affected = eng.execute(Path("/f.hyper"), "DELETE FROM t WHERE x = 1")

    assert affected == 7
    assert fake.connection.commands == ["DELETE FROM t WHERE x = 1"]


# -- 31–32: introspecção do catálogo -------------------------------------------


def test_describe_lista_todos_schemas_e_tabelas_com_colunas(fake: FakeHapi) -> None:
    schema = FakeSchemaName("Extract")
    table_a = FakeTableName("Extract", "A")
    table_b = FakeTableName("Extract", "B")
    fake.connection.catalog.schema_names = [schema]
    fake.connection.catalog.table_names = {str(schema): [table_a, table_b]}
    fake.connection.catalog.table_definitions[str(table_a)] = FakeTableDefinition(
        table_a, [FakeColumn("x", FakeSqlType("TEXT"))]
    )
    fake.connection.catalog.table_definitions[str(table_b)] = FakeTableDefinition(
        table_b, [FakeColumn("y", FakeSqlType("BIG_INT"))]
    )
    fake.connection.scalar_return = 5

    with engine.hyper_session() as eng:
        reports = eng.describe(Path("/f.hyper"))

    assert [r.table_name for r in reports] == ["A", "B"]
    assert reports[0].schema_name == "Extract"
    assert reports[0].columns[0].name == "x"
    assert reports[1].columns[0].type == "big_int"
    assert reports[0].row_count == 5


def test_describe_contagem_de_linhas_falha_vira_none_sem_abortar(
    fake: FakeHapi,
) -> None:
    schema = FakeSchemaName("Extract")
    table = FakeTableName("Extract", "A")
    fake.connection.catalog.schema_names = [schema]
    fake.connection.catalog.table_names = {str(schema): [table]}
    fake.connection.catalog.table_definitions[str(table)] = FakeTableDefinition(
        table, [FakeColumn("x", FakeSqlType("TEXT"))]
    )
    fake.connection.scalar_error = FakeHyperException("count falhou")

    with engine.hyper_session() as eng:
        reports = eng.describe(Path("/f.hyper"))

    assert len(reports) == 1
    assert reports[0].row_count is None
    assert reports[0].columns[0].name == "x"


# -- Identificadores sem aspas de citação --------------------------------------


def test_identifier_usa_unescaped_do_hyper_name_quando_disponivel() -> None:
    """`Name` do Hyper cita em `str()`; o contrato deve expor o nome cru.

    Regressão: com o runtime real, `str(Name("cidade"))` retorna `"cidade"`
    (com aspas), vazando aspas para os nomes de coluna/tabela expostos ao agente.
    """

    class _NameLike:
        unescaped = "cidade"

        def __str__(self) -> str:
            return '"cidade"'

    assert engine._identifier(_NameLike()) == "cidade"
    # Duplos de teste e nomes já em `str` puro não têm `.unescaped`.
    assert engine._identifier("plain") == "plain"


# -- 33–34: tradução de erros --------------------------------------------------


def test_hyper_exception_traduzida_para_hyper_engine_error_com_mensagem_original(
    fake: FakeHapi,
) -> None:
    fake.connection.command_error = FakeHyperException("syntax error near 'SELCT'")

    with engine.hyper_session() as eng:
        with pytest.raises(engine.HyperEngineError) as exc_info:
            eng.execute(Path("/f.hyper"), "SELCT 1")

    assert exc_info.value.code == ErrorCode.HYPER_SQL_ERROR
    assert "syntax error near 'SELCT'" in exc_info.value.message


def test_arquivo_nao_hyper_traduzido_para_hyper_invalid_file(fake: FakeHapi) -> None:
    fake.connection.command_error = FakeHyperException(
        'The database "x.hyper" could not open: not a valid Hyper file'
    )

    with engine.hyper_session() as eng:
        with pytest.raises(engine.HyperEngineError) as exc_info:
            eng.execute(Path("/f.hyper"), "SELECT 1")

    assert exc_info.value.code == ErrorCode.HYPER_INVALID_FILE


def test_hyper_error_remove_paths_internos_do_runtime(fake: FakeHapi) -> None:
    fake.connection.command_error = FakeHyperException(
        "internal failure at /opt/hyper/hyperd/bin/hyperd while running"
    )

    with engine.hyper_session() as eng:
        with pytest.raises(engine.HyperEngineError) as exc_info:
            eng.execute(Path("/f.hyper"), "SELECT 1")

    assert "hyperd" not in exc_info.value.message
    assert "internal failure" in exc_info.value.message

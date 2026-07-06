"""Testes unitários da extração de bancos externos (`hyper/db.py`).

O SQLAlchemy e o runtime Hyper (`tableauhyperapi`) são inteiramente mockados: um
engine falso entrega lotes controlados via `fetchmany`, e um `FakeHapi` injetado
em `db.hapi` grava os lotes num `Inserter` de teste — sem rede, sem banco real e
sem o binário Hyper. Cobrem os casos 35–45 da techspec.

O foco de segurança (RF11): asserções dedicadas garantem que nenhuma connection
string (nem suas partes) vaza em exceções, logs (`caplog`) ou retornos.
"""

from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_tableau.hyper import db
from mcp_tableau.models import ErrorCode

# Connection string usada nos testes; nenhuma parte dela pode vazar.
_URL = "postgresql+psycopg://vendas_user:s3nh4-secreta@db.interno:5432/dw"
_URL_PARTS = ("vendas_user", "s3nh4-secreta", "db.interno", _URL)

# Registros das conexões/inserters Hyper criados pelo `db.py` sob teste, para
# inspeção pós-execução (limpos pela fixture `fake_hapi`).
_HYPER_CONNECTIONS: list[FakeConnection] = []
_HYPER_INSERTERS: list[FakeInserter] = []


# -- Duplos de teste do tableauhyperapi ---------------------------------------


class FakeSqlType:
    """`SqlType` de teste que expõe `.tag.name` (como o `TypeTag` do Hyper)."""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    def __repr__(self) -> str:  # pragma: no cover - só para diagnóstico
        return f"FakeSqlType({self.tag})"


class FakeSqlTypeFactory:
    """Espelha `SqlType.text()`, `SqlType.big_int()`, etc."""

    text = staticmethod(lambda: FakeSqlType("TEXT"))
    big_int = staticmethod(lambda: FakeSqlType("BIG_INT"))
    double = staticmethod(lambda: FakeSqlType("DOUBLE"))
    bool = staticmethod(lambda: FakeSqlType("BOOL"))
    date = staticmethod(lambda: FakeSqlType("DATE"))
    timestamp = staticmethod(lambda: FakeSqlType("TIMESTAMP"))
    timestamp_tz = staticmethod(lambda: FakeSqlType("TIMESTAMP_TZ"))


class FakeColumn:
    """Coluna de `TableDefinition` com nome e tipo."""

    def __init__(self, name: str, type: FakeSqlType, nullability: object) -> None:
        self.name = name
        self.type = type
        self.nullability = nullability


class FakeTableDefinition:
    """`TableDefinition` de teste que guarda nome qualificado e colunas."""

    Column = FakeColumn

    def __init__(self, table_name: object, columns: list[FakeColumn]) -> None:
        self.table_name = table_name
        self.columns = columns


class FakeInserter:
    """`Inserter` de teste: acumula os lotes e registra a chamada de `execute`."""

    def __init__(self, conn: FakeConnection, definition: FakeTableDefinition) -> None:
        self.conn = conn
        self.definition = definition
        self.rows: list[list[object]] = []
        self.executed = False
        _HYPER_INSERTERS.append(self)

    def __enter__(self) -> FakeInserter:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def add_rows(self, rows: list[list[object]]) -> None:
        self.rows.extend([list(row) for row in rows])

    def execute(self) -> None:
        self.executed = True


class FakeCatalog:
    """Catálogo de teste que registra a definição de tabela criada."""

    def __init__(self) -> None:
        self.created_schema: object = None
        self.created_definition: FakeTableDefinition | None = None

    def create_schema_if_not_exists(self, schema: object) -> None:
        self.created_schema = schema

    def create_table(self, definition: FakeTableDefinition) -> None:
        self.created_definition = definition


class FakeConnection:
    """`Connection` de teste que expõe um catálogo e captura o `create_mode`."""

    def __init__(self, endpoint: object, database: str, create_mode: object) -> None:
        self.endpoint = endpoint
        self.database = database
        self.create_mode = create_mode
        self.catalog = FakeCatalog()
        _HYPER_CONNECTIONS.append(self)

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class FakeProcess:
    """`HyperProcess` de teste (context manager) com `endpoint`."""

    endpoint = object()

    def __init__(self, telemetry: object) -> None:
        self.telemetry = telemetry

    def __enter__(self) -> FakeProcess:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class FakeTelemetry:
    DO_NOT_SEND_USAGE_DATA_TO_TABLEAU = object()


class FakeCreateMode:
    CREATE_AND_REPLACE = object()


class FakeHapi:
    """Módulo `tableauhyperapi` falso, com o subconjunto usado por `db.py`."""

    HyperProcess = FakeProcess
    Connection = FakeConnection
    Inserter = FakeInserter
    TableDefinition = FakeTableDefinition
    SqlType = FakeSqlTypeFactory
    Telemetry = FakeTelemetry
    CreateMode = FakeCreateMode
    NULLABLE = object()

    @staticmethod
    def SchemaName(name: str) -> str:  # noqa: N802 - espelha a API do Hyper
        return name

    @staticmethod
    def TableName(schema: str, table: str) -> str:  # noqa: N802 - idem
        return f'"{schema}"."{table}"'


# -- Duplos de teste do SQLAlchemy --------------------------------------------


class FakeResult:
    """`CursorResult` de teste: entrega os lotes via `fetchmany`."""

    def __init__(self, keys: list[str], batches: list[list[list[object]]]) -> None:
        self._keys = keys
        self._batches = list(batches)
        self.fetchmany_sizes: list[int] = []

    def keys(self) -> list[str]:
        return list(self._keys)

    def fetchmany(self, size: int) -> list[list[object]]:
        self.fetchmany_sizes.append(size)
        if self._batches:
            return self._batches.pop(0)
        return []


class FakeConn:
    """Conexão SQLAlchemy de teste (context manager) com `execution_options`."""

    def __init__(self, result: FakeResult) -> None:
        self._result = result
        self.exec_options: dict[str, object] = {}
        self.executed_query: object = None

    def __enter__(self) -> FakeConn:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execution_options(self, **kwargs: object) -> FakeConn:
        self.exec_options.update(kwargs)
        return self

    def execute(self, query: object) -> FakeResult:
        self.executed_query = query
        return self._result


class FakeEngine:
    """Engine SQLAlchemy de teste que devolve sempre a mesma conexão."""

    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn
        self.disposed = False

    def connect(self) -> FakeConn:
        return self._conn

    def dispose(self) -> None:
        self.disposed = True


@pytest.fixture
def fake_hapi(monkeypatch: pytest.MonkeyPatch) -> type[FakeHapi]:
    """Injeta o `FakeHapi` em `db.hapi` para a suíte rápida (sem runtime real)."""
    _HYPER_CONNECTIONS.clear()
    _HYPER_INSERTERS.clear()
    monkeypatch.setattr(db, "hapi", FakeHapi)
    return FakeHapi


def _patch_engine(
    monkeypatch: pytest.MonkeyPatch,
    keys: list[str],
    batches: list[list[list[object]]],
) -> tuple[FakeEngine, FakeConn, FakeResult]:
    """Monkeypatcha `db.create_engine`/`db.text` para entregar lotes controlados."""
    result = FakeResult(keys, batches)
    conn = FakeConn(result)
    engine = FakeEngine(conn)
    created: dict[str, object] = {}

    def _create_engine(url: str, **kwargs: object) -> FakeEngine:
        created["url"] = url
        created["kwargs"] = kwargs
        return engine

    monkeypatch.setattr(db, "create_engine", _create_engine)
    monkeypatch.setattr(db, "text", lambda sql: ("TEXT", sql))
    engine.created = created  # type: ignore[attr-defined]
    return engine, conn, result


# -- resolve_connection --------------------------------------------------------


def test_resolve_connection_le_variavel_com_nome_uppercase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)

    # Nome em minúsculas deve resolver para a variável em maiúsculas.
    assert db.resolve_connection("vendas") == _URL
    assert db.resolve_connection("VENDAS") == _URL


def test_resolve_connection_ausente_levanta_db_connection_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HYPER_DB_CONN_FINANCEIRO", raising=False)

    with pytest.raises(db.DbConfigError) as exc_info:
        db.resolve_connection("financeiro")

    assert exc_info.value.code is ErrorCode.DB_CONNECTION_NOT_CONFIGURED
    # Cita o nome lógico e o nome da variável esperada.
    assert "FINANCEIRO" in exc_info.value.message
    assert "HYPER_DB_CONN_FINANCEIRO" in exc_info.value.message


def test_resolve_connection_nao_loga_nem_inclui_url_na_excecao(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)

    with caplog.at_level(logging.DEBUG, logger="mcp_tableau.hyper.db"):
        db.resolve_connection("vendas")
        # Ausente: a mensagem de erro não pode conter a URL.
        with pytest.raises(db.DbConfigError) as exc_info:
            db.resolve_connection("secreta")

    for part in _URL_PARTS:
        assert part not in exc_info.value.message
        assert part not in caplog.text


# -- extract_to_hyper: streaming e mapeamento de tipos -------------------------


def test_extract_to_hyper_usa_stream_results_e_lotes(
    monkeypatch: pytest.MonkeyPatch, fake_hapi: type[FakeHapi], tmp_path: Path
) -> None:
    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)
    # Dois lotes de 2 linhas + um vazio (fim do cursor).
    batches = [[[1, "a"], [2, "b"]], [[3, "c"], [4, "d"]]]
    engine, conn, result = _patch_engine(monkeypatch, ["id", "nome"], batches)

    report = db.extract_to_hyper(
        "vendas", "SELECT * FROM t", tmp_path / "e.hyper", "Extract", batch_size=2
    )

    assert report.row_count == 4
    assert conn.exec_options["stream_results"] is True
    # Leitura em lotes do tamanho pedido (primeiro + drenagem do cursor).
    assert all(size == 2 for size in result.fetchmany_sizes)
    assert engine.created["kwargs"]["pool_pre_ping"] is True  # type: ignore[index]
    assert engine.disposed is True


def test_extract_to_hyper_mapeia_tipos_do_cursor_para_sqltype(
    monkeypatch: pytest.MonkeyPatch, fake_hapi: type[FakeHapi], tmp_path: Path
) -> None:
    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)
    row = [
        1,
        "texto",
        3.5,
        True,
        datetime.date(2026, 1, 2),
        datetime.datetime(2026, 1, 2, 3, 4, 5),
        Decimal("10.50"),
    ]
    keys = ["i", "s", "f", "b", "d", "ts", "num"]
    _patch_engine(monkeypatch, keys, [[row]])

    report = db.extract_to_hyper(
        "vendas", "SELECT * FROM t", tmp_path / "e.hyper", "Extract"
    )

    tipos = [c.type for c in report.columns]
    assert tipos == [
        "big_int",
        "text",
        "double",
        "bool",
        "date",
        "timestamp",
        "double",
    ]
    definition = _HYPER_CONNECTIONS[-1].catalog.created_definition
    assert definition is not None
    assert [col.type.tag for col in definition.columns] == [
        "BIG_INT",
        "TEXT",
        "DOUBLE",
        "BOOL",
        "DATE",
        "TIMESTAMP",
        "DOUBLE",
    ]


def test_extract_to_hyper_tipo_exotico_faz_fallback_para_text(
    monkeypatch: pytest.MonkeyPatch, fake_hapi: type[FakeHapi], tmp_path: Path
) -> None:
    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)

    class Exotico:
        def __str__(self) -> str:
            return "valor-exotico"

    _patch_engine(monkeypatch, ["c"], [[[Exotico()]]])

    report = db.extract_to_hyper(
        "vendas", "SELECT * FROM t", tmp_path / "e.hyper", "Extract"
    )

    assert report.columns[0].type == "text"
    assert report.warnings  # aviso de fallback presente
    assert "text" in report.warnings[0]
    # O valor exótico foi convertido para str antes de ser gravado no extrato.
    assert _HYPER_INSERTERS[-1].rows == [["valor-exotico"]]
    assert _HYPER_INSERTERS[-1].executed is True


def test_resultado_vazio_cria_hyper_com_zero_linhas_sem_erro(
    monkeypatch: pytest.MonkeyPatch, fake_hapi: type[FakeHapi], tmp_path: Path
) -> None:
    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)
    _patch_engine(monkeypatch, ["id", "nome"], [])

    report = db.extract_to_hyper(
        "vendas", "SELECT * FROM t WHERE 1=0", tmp_path / "e.hyper", "Extract"
    )

    assert report.row_count == 0
    assert report.warnings == []
    # A tabela foi criada mesmo sem linhas, com todas as colunas em text.
    definition = _HYPER_CONNECTIONS[-1].catalog.created_definition
    assert definition is not None
    assert [c.name for c in definition.columns] == ["id", "nome"]
    assert [c.type.tag for c in definition.columns] == ["TEXT", "TEXT"]


# -- extract_to_hyper: classificação e sanitização de erros --------------------


def _make_engine_raising(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    """Monkeypatcha `create_engine` para levantar `exc` ao conectar."""

    def _create_engine(url: str, **kwargs: object) -> object:
        engine = MagicMock(name="engine")
        engine.connect.side_effect = exc
        return engine

    monkeypatch.setattr(db, "create_engine", _create_engine)
    monkeypatch.setattr(db, "text", lambda sql: sql)


def test_operational_error_de_rede_vira_db_connection_failed(
    monkeypatch: pytest.MonkeyPatch, fake_hapi: type[FakeHapi], tmp_path: Path
) -> None:
    from sqlalchemy.exc import OperationalError

    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)
    exc = OperationalError(
        "SELECT 1", {}, Exception("could not connect to server: Connection refused")
    )
    _make_engine_raising(monkeypatch, exc)

    with pytest.raises(db.DbError) as exc_info:
        db.extract_to_hyper("vendas", "SELECT 1", tmp_path / "e.hyper", "Extract")

    assert exc_info.value.code is ErrorCode.DB_CONNECTION_FAILED


def test_erro_de_autenticacao_vira_db_auth_failed(
    monkeypatch: pytest.MonkeyPatch, fake_hapi: type[FakeHapi], tmp_path: Path
) -> None:
    from sqlalchemy.exc import OperationalError

    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)
    exc = OperationalError(
        "SELECT 1",
        {},
        Exception('password authentication failed for user "vendas_user"'),
    )
    _make_engine_raising(monkeypatch, exc)

    with pytest.raises(db.DbError) as exc_info:
        db.extract_to_hyper("vendas", "SELECT 1", tmp_path / "e.hyper", "Extract")

    assert exc_info.value.code is ErrorCode.DB_AUTH_FAILED
    # Mesmo citando o usuário, a mensagem é sanitizada.
    assert "vendas_user" not in exc_info.value.message


def test_programming_error_vira_db_query_error_com_mensagem_sanitizada(
    monkeypatch: pytest.MonkeyPatch, fake_hapi: type[FakeHapi], tmp_path: Path
) -> None:
    from sqlalchemy.exc import ProgrammingError

    monkeypatch.setenv("HYPER_DB_CONN_VENDAS", _URL)
    exc = ProgrammingError(
        "SELECT inexistente",
        {},
        Exception(f'column "inexistente" does not exist [url={_URL}]'),
    )
    _make_engine_raising(monkeypatch, exc)

    with pytest.raises(db.DbError) as exc_info:
        db.extract_to_hyper(
            "vendas", "SELECT inexistente", tmp_path / "e.hyper", "Extract"
        )

    assert exc_info.value.code is ErrorCode.DB_QUERY_ERROR
    # A causa do SQL é preservada, mas a URL é removida.
    assert "inexistente" in exc_info.value.message
    for part in _URL_PARTS:
        assert part not in exc_info.value.message


def test_sanitizacao_remove_url_usuario_senha_e_host_da_mensagem() -> None:
    raw = (
        f"connection to {_URL} failed: user vendas_user with password "
        "s3nh4-secreta rejected by db.interno"
    )

    sanitized = db._sanitize(raw, _URL)

    for part in _URL_PARTS:
        assert part not in sanitized
    assert "<redacted>" in sanitized

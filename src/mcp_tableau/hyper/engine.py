"""Motor Hyper (`HyperEngine`) — wrapper de alto nível da `tableauhyperapi`.

Único componente que fala com o runtime local do Hyper (`HyperProcess`,
`Connection`, `Inserter`, catálogo), análogo a `tableau/client.py` para o REST.
Centraliza:

- ciclo de vida do processo Hyper via o context manager `hyper_session()`, que
  inicia um `HyperProcess` **por chamada** (telemetria desativada) e o encerra ao
  final, inclusive em caso de exceção — sem estado residente entre chamadas;
- criação de tabela a partir de arquivo (CSV com schema via `COPY FROM`; CSV sem
  schema e Parquet via `CREATE TABLE ... AS SELECT * FROM external(...)`) e a
  partir de linhas inline (via `Inserter`);
- append com validação prévia de compatibilidade de schema;
- consulta de leitura com detecção de truncamento (`max_rows + 1`) e serialização
  de tipos para JSON (datas em ISO-8601, `NUMERIC` como `str`);
- execução de comandos com contagem de linhas afetadas e introspecção do catálogo;
- tradução de `HyperException` para `HyperEngineError(code, message)`, preservando
  a mensagem do motor e **sem** vazar paths internos do runtime.

O `tableauhyperapi` traz um runtime binário pesado (~150 MB) e não está presente
na suíte rápida/CI. Por isso o import é tolerante à ausência da biblioteca
(``hapi is None``); as funções levantam um erro acionável se invocadas sem o
runtime, e os testes injetam um módulo falso em ``hapi``.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from mcp_tableau.models import ErrorCode, HyperColumn, InlineColumn

if TYPE_CHECKING:  # pragma: no cover - apenas tipagem
    from collections.abc import Sequence

try:  # pragma: no cover - depende do runtime instalado
    import tableauhyperapi as hapi
except ImportError:  # pragma: no cover - runtime ausente na suíte rápida/CI
    hapi = None  # type: ignore[assignment]

# Schema padrão das tabelas Hyper: compatibilidade com Tableau Server antigos.
EXTRACT_SCHEMA = "Extract"

# `numeric(p,s)` do contrato → precisão/escala para `SqlType.numeric(p, s)`.
_NUMERIC_RE = re.compile(r"^numeric\(\s*(\d+)\s*,\s*(\d+)\s*\)$")

# `TypeTag` do Hyper → tipo lógico do contrato. Tipos ausentes deste mapa são
# expostos na inspeção pelo nome bruto do tag (somente leitura, ex.: geography).
_TAG_TO_CONTRACT = {
    "BOOL": "bool",
    "SMALL_INT": "big_int",
    "INT": "big_int",
    "BIG_INT": "big_int",
    "DOUBLE": "double",
    "NUMERIC": "numeric",
    "DATE": "date",
    "TIMESTAMP": "timestamp",
    "TIMESTAMP_TZ": "timestamp_tz",
    "TEXT": "text",
    "VARCHAR": "text",
    "CHAR": "text",
    "JSON": "text",
}

# Marcadores de path do runtime Hyper que jamais podem vazar em mensagens de erro.
_RUNTIME_PATH_RE = re.compile(r"(?:/|\\)\S*hyperd\S*", re.IGNORECASE)

# Palavras-chave que caracterizam um arquivo `.hyper` inválido/ilegível.
_INVALID_FILE_MARKERS = (
    "not a valid",
    "not a database",
    "could not open",
    "unable to open",
    "unknown file format",
    "corrupt",
    "invalid file",
)

# Valor escalar admitido numa célula de resultado serializado.
Scalar = str | int | float | bool | None


class HyperEngineError(Exception):
    """Erro do motor Hyper já traduzido para um `ErrorCode` acionável.

    As tools consomem `code` para montar o envelope `ToolError`. A `message`
    preserva a causa do motor, porém nunca contém paths internos do runtime nem
    dados sensíveis.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# -- Objetos de requisição/relatório da camada de engine -----------------------


@dataclass(slots=True)
class FileIngestRequest:
    """Parâmetros de criação de tabela a partir de um arquivo CSV/Parquet."""

    source_path: Path
    hyper_path: Path
    table_name: str = "Extract"
    source_format: Literal["csv", "parquet"] = "csv"
    delimiter: str = ","
    encoding: str = "utf-8"
    header: bool = True
    schema: list[InlineColumn] | None = None


@dataclass(slots=True)
class InlineIngestRequest:
    """Parâmetros de criação de tabela a partir de colunas + linhas inline."""

    hyper_path: Path
    table_name: str
    columns: list[InlineColumn]
    rows: list[list[object]]
    create_mode: Literal["replace", "if_not_exists"] = "replace"


@dataclass(slots=True)
class AppendRequest:
    """Parâmetros de append de linhas inline numa tabela existente."""

    hyper_path: Path
    table_name: str
    columns: list[InlineColumn]
    rows: list[list[object]]


@dataclass(slots=True)
class TableReport:
    """Descrição estrutural de uma tabela (criada ou inspecionada).

    `row_count` é `None` quando a contagem não é determinável sem abortar o
    relatório (ex.: falha ao contar linhas de uma tabela específica).
    """

    schema_name: str
    table_name: str
    columns: list[HyperColumn] = field(default_factory=list)
    row_count: int | None = None


@dataclass(slots=True)
class QueryRows:
    """Resultado bruto de uma consulta de leitura, já serializado para JSON."""

    columns: list[HyperColumn] = field(default_factory=list)
    rows: list[list[Scalar]] = field(default_factory=list)
    truncated: bool = False


# -- Sessão e engine -----------------------------------------------------------


def _require_runtime() -> None:
    """Garante que o runtime Hyper está disponível antes de qualquer operação."""
    if hapi is None:
        raise HyperEngineError(
            ErrorCode.HYPER_SQL_ERROR,
            "Runtime Hyper (tableauhyperapi) não está instalado neste ambiente.",
        )


@contextmanager
def hyper_session() -> Iterator[HyperEngine]:
    """Inicia um `HyperProcess` (telemetria off) e entrega o `HyperEngine`.

    O processo é iniciado por chamada e encerrado ao sair do bloco, inclusive em
    caso de exceção — não há processo Hyper residente entre chamadas.
    """
    _require_runtime()
    with hapi.HyperProcess(
        telemetry=hapi.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU
    ) as process:
        yield HyperEngine(process)


class HyperEngine:
    """Operações de alto nível sobre `.hyper`, ligadas a um `HyperProcess` vivo.

    Cada operação abre sua própria `Connection` com o `create_mode` adequado
    (criação, append/consulta), pois o modo varia por operação. Use sempre via
    :func:`hyper_session`, que garante o encerramento do processo.
    """

    def __init__(self, process: object) -> None:
        self._process = process

    # -- Criação ---------------------------------------------------------------

    def create_table_from_file(self, req: FileIngestRequest) -> TableReport:
        """Cria a tabela a partir de um arquivo CSV/Parquet.

        Com `req.schema`, cria a `TableDefinition` explícita e carrega via
        `COPY FROM`. Sem schema (CSV) ou para Parquet, infere via
        `CREATE TABLE ... AS SELECT * FROM external(...)`.
        """
        table = self._table_name(req.table_name)
        with self._connect(req.hyper_path, hapi.CreateMode.CREATE_AND_REPLACE) as conn:
            with self._wrap_errors():
                conn.catalog.create_schema_if_not_exists(
                    hapi.SchemaName(EXTRACT_SCHEMA)
                )
                if req.schema is not None:
                    count = self._load_with_copy(conn, table, req)
                else:
                    count = self._load_with_external(conn, table, req)
                columns = self._read_columns(conn, table)
            return TableReport(EXTRACT_SCHEMA, req.table_name, columns, count)

    def create_table_from_rows(self, req: InlineIngestRequest) -> TableReport:
        """Cria a tabela a partir de colunas + linhas inline via `Inserter`."""
        table = self._table_name(req.table_name)
        mode = (
            hapi.CreateMode.CREATE_AND_REPLACE
            if req.create_mode == "replace"
            else hapi.CreateMode.CREATE_IF_NOT_EXISTS
        )
        with self._connect(req.hyper_path, mode) as conn:
            with self._wrap_errors():
                conn.catalog.create_schema_if_not_exists(
                    hapi.SchemaName(EXTRACT_SCHEMA)
                )
                definition = self._table_definition(table, req.columns)
                conn.catalog.create_table(definition)
                self._insert_rows(conn, definition, req.rows)
            columns = [self._column_from_inline(col) for col in req.columns]
            return TableReport(EXTRACT_SCHEMA, req.table_name, columns, len(req.rows))

    # -- Append ----------------------------------------------------------------

    def append_rows(self, req: AppendRequest) -> int:
        """Faz append de linhas inline validando o schema **antes** de inserir.

        Levanta `HyperEngineError(HYPER_SCHEMA_MISMATCH)` se as colunas informadas
        não forem compatíveis (contagem, nomes e tipos base) com a tabela alvo.
        """
        table = self._table_name(req.table_name)
        with self._connect(req.hyper_path, hapi.CreateMode.NONE) as conn:
            with self._wrap_errors():
                existing = conn.catalog.get_table_definition(table)
            self._assert_compatible(existing, req.columns)
            with self._wrap_errors():
                self._insert_rows(conn, existing, req.rows)
            return len(req.rows)

    # -- Leitura ---------------------------------------------------------------

    def query(self, hyper_path: Path, sql: str, max_rows: int) -> QueryRows:
        """Executa uma consulta de leitura, lendo `max_rows + 1` para truncamento.

        Serializa `DATE`/`TIMESTAMP` como ISO-8601 e `NUMERIC` como `str`.
        """
        with self._connect(hyper_path, hapi.CreateMode.NONE) as conn:
            with self._wrap_errors():
                rows: list[list[Scalar]] = []
                truncated = False
                with conn.execute_query(sql) as result:
                    columns = [
                        self._column_from_sql(col) for col in result.schema.columns
                    ]
                    for index, row in enumerate(result):
                        if index >= max_rows:
                            truncated = True
                            break
                        rows.append([_serialize(value) for value in row])
            return QueryRows(columns=columns, rows=rows, truncated=truncated)

    def describe(self, hyper_path: Path) -> list[TableReport]:
        """Lista todos os schemas/tabelas do `.hyper` com colunas e contagens.

        A contagem de uma tabela que falha vira `None`, sem abortar o relatório.
        """
        reports: list[TableReport] = []
        with self._connect(hyper_path, hapi.CreateMode.NONE) as conn:
            with self._wrap_errors():
                schemas = conn.catalog.get_schema_names()
            for schema in schemas:
                with self._wrap_errors():
                    tables = conn.catalog.get_table_names(schema)
                for table in tables:
                    with self._wrap_errors():
                        definition = conn.catalog.get_table_definition(table)
                        columns = [
                            self._column_from_sql(col) for col in definition.columns
                        ]
                    reports.append(
                        TableReport(
                            schema_name=self._leaf_name(schema),
                            table_name=self._leaf_name(table),
                            columns=columns,
                            row_count=self._safe_row_count(conn, table),
                        )
                    )
        return reports

    # -- Mutação ---------------------------------------------------------------

    def execute(self, hyper_path: Path, sql: str) -> int | None:
        """Executa um comando de mutação/DDL e retorna as linhas afetadas."""
        with self._connect(hyper_path, hapi.CreateMode.NONE) as conn:
            with self._wrap_errors():
                return conn.execute_command(sql)

    # -- Helpers de carga ------------------------------------------------------

    def _load_with_copy(
        self, conn: object, table: object, req: FileIngestRequest
    ) -> int:
        """CSV com schema explícito: cria a tabela e carrega via `COPY FROM`."""
        assert req.schema is not None  # garantido pelo chamador
        definition = self._table_definition(table, req.schema)
        conn.catalog.create_table(definition)
        path_literal = hapi.escape_string_literal(str(req.source_path))
        delimiter = hapi.escape_string_literal(req.delimiter)
        encoding = hapi.escape_string_literal(req.encoding)
        header = "true" if req.header else "false"
        command = (
            f"COPY {table} FROM {path_literal} "
            f"WITH (format => 'csv', delimiter => {delimiter}, "
            f"encoding => {encoding}, header => {header})"
        )
        count = conn.execute_command(command)
        return int(count) if count is not None else 0

    def _load_with_external(
        self, conn: object, table: object, req: FileIngestRequest
    ) -> int:
        """CSV sem schema / Parquet: infere o schema via `external()`."""
        path_literal = hapi.escape_string_literal(str(req.source_path))
        if req.source_format == "parquet":
            external = f"external({path_literal})"
        else:
            delimiter = hapi.escape_string_literal(req.delimiter)
            header = "true" if req.header else "false"
            external = (
                f"external({path_literal}, format => 'csv', "
                f"delimiter => {delimiter}, header => {header})"
            )
        command = f"CREATE TABLE {table} AS SELECT * FROM {external}"
        count = conn.execute_command(command)
        return int(count) if count is not None else 0

    def _insert_rows(
        self, conn: object, definition: object, rows: Sequence[Sequence[object]]
    ) -> None:
        """Insere linhas via `Inserter`, respeitando a definição da tabela."""
        with hapi.Inserter(conn, definition) as inserter:
            inserter.add_rows(rows)
            inserter.execute()

    def _safe_row_count(self, conn: object, table: object) -> int | None:
        """Conta linhas de uma tabela; devolve `None` se a contagem falhar."""
        try:
            count = conn.execute_scalar_query(f"SELECT COUNT(*) FROM {table}")
        except Exception:  # noqa: BLE001 - contagem tolerante a falha (RF16)
            return None
        return int(count) if count is not None else None

    # -- Helpers de schema/tipos -----------------------------------------------

    def _connect(self, hyper_path: Path, create_mode: object) -> object:
        """Abre uma `Connection` ao arquivo `.hyper` com o `create_mode` dado."""
        return hapi.Connection(
            endpoint=self._process.endpoint,
            database=str(hyper_path),
            create_mode=create_mode,
        )

    def _table_name(self, table_name: str) -> object:
        """Nome qualificado ``"Extract"."<table>"`` como `TableName` do Hyper."""
        return hapi.TableName(EXTRACT_SCHEMA, table_name)

    def _table_definition(
        self, table: object, columns: Sequence[InlineColumn]
    ) -> object:
        """Monta a `TableDefinition` a partir de colunas do contrato."""
        cols = [
            hapi.TableDefinition.Column(
                col.name,
                self._sql_type(col.type),
                hapi.NULLABLE if col.nullable else hapi.NOT_NULLABLE,
            )
            for col in columns
        ]
        return hapi.TableDefinition(table, cols)

    def _sql_type(self, type_str: str) -> object:
        """Contrato → `SqlType` (tabela de mapeamento da techspec)."""
        factory = {
            "text": hapi.SqlType.text,
            "big_int": hapi.SqlType.big_int,
            "double": hapi.SqlType.double,
            "bool": hapi.SqlType.bool,
            "date": hapi.SqlType.date,
            "timestamp": hapi.SqlType.timestamp,
            "timestamp_tz": hapi.SqlType.timestamp_tz,
        }.get(type_str)
        if factory is not None:
            return factory()
        match = _NUMERIC_RE.match(type_str)
        if match is not None:
            return hapi.SqlType.numeric(int(match.group(1)), int(match.group(2)))
        # `InlineColumn` já valida o contrato; este ramo é defensivo.
        raise HyperEngineError(
            ErrorCode.HYPER_SCHEMA_MISMATCH,
            f"Tipo de coluna não suportado pelo motor Hyper: '{type_str}'.",
        )

    def _read_columns(self, conn: object, table: object) -> list[HyperColumn]:
        """Lê as colunas efetivas da tabela (inferidas ou declaradas)."""
        definition = conn.catalog.get_table_definition(table)
        return [self._column_from_sql(col) for col in definition.columns]

    def _column_from_sql(self, column: object) -> HyperColumn:
        """Coluna do catálogo/resultado → `HyperColumn` do contrato."""
        return HyperColumn(
            name=_identifier(column.name),
            type=self._contract_type(column.type),
            nullable=self._is_nullable(column),
        )

    def _column_from_inline(self, column: InlineColumn) -> HyperColumn:
        """`InlineColumn` (entrada) → `HyperColumn` (saída)."""
        return HyperColumn(name=column.name, type=column.type, nullable=column.nullable)

    def _contract_type(self, sql_type: object) -> str:
        """`SqlType` → tipo lógico do contrato; tag desconhecido vira o nome bruto."""
        tag = getattr(sql_type, "tag", None)
        tag_name = getattr(tag, "name", None) or str(tag)
        return _TAG_TO_CONTRACT.get(tag_name.upper(), tag_name.lower())

    def _is_nullable(self, column: object) -> bool:
        """Nulabilidade da coluna; assume `True` quando não determinável."""
        nullability = getattr(column, "nullability", None)
        if nullability is None:
            return True
        return nullability == hapi.NULLABLE

    def _assert_compatible(
        self, existing: object, incoming: Sequence[InlineColumn]
    ) -> None:
        """Valida compatibilidade de schema (contagem, nomes e tipos base)."""
        existing_cols = [
            (_identifier(col.name), self._contract_type(col.type))
            for col in existing.columns
        ]
        if len(existing_cols) != len(incoming):
            raise HyperEngineError(
                ErrorCode.HYPER_SCHEMA_MISMATCH,
                "Schema incompatível: a tabela alvo tem "
                f"{len(existing_cols)} coluna(s), mas foram informadas "
                f"{len(incoming)}.",
            )
        for (exp_name, exp_type), col in zip(existing_cols, incoming, strict=True):
            names_differ = exp_name != col.name
            types_differ = _base_type(exp_type) != _base_type(col.type)
            if names_differ or types_differ:
                raise HyperEngineError(
                    ErrorCode.HYPER_SCHEMA_MISMATCH,
                    "Schema incompatível na coluna "
                    f"'{col.name}': a tabela alvo espera "
                    f"'{exp_name}' ({exp_type}).",
                )

    @staticmethod
    def _leaf_name(named: object) -> str:
        """Nome simples de um `SchemaName`/`TableName` (sem qualificação nem aspas)."""
        name = getattr(named, "name", None)
        return _identifier(name) if name is not None else _identifier(named)

    # -- Tradução de erros -----------------------------------------------------

    @contextmanager
    def _wrap_errors(self) -> Iterator[None]:
        """Converte `HyperException` do bloco em `HyperEngineError` traduzido."""
        try:
            yield
        except hapi.HyperException as exc:  # type: ignore[union-attr]
            raise _translate(exc) from exc


# -- Funções puras auxiliares --------------------------------------------------


def _serialize(value: object) -> Scalar:
    """Serializa um valor do motor para tipos JSON-safe.

    `date`/`datetime` viram ISO-8601 e `Decimal` vira `str` (preserva precisão);
    os demais escalares (`int`, `float`, `bool`, `str`, `None`) passam direto.
    """
    if isinstance(value, datetime.date):  # cobre também datetime.datetime
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _identifier(name: object) -> str:
    """Nome de identificador cru, sem as aspas de citação do Hyper.

    O `Name` do Hyper serializa citado em `str()` (ex.: ``"cidade"``); usamos
    `.unescaped` para expor o nome limpo no contrato. Duplos de teste e nomes já
    em `str` puro não têm `.unescaped` — daí o fallback para `str()`.
    """
    unescaped = getattr(name, "unescaped", None)
    return str(unescaped) if unescaped is not None else str(name)


def _base_type(type_str: str) -> str:
    """Tipo base do contrato, ignorando parâmetros (ex.: `numeric(10,2)`)."""
    return type_str.split("(", 1)[0].strip()


def _scrub_runtime_paths(message: str) -> str:
    """Remove paths internos do runtime Hyper de uma mensagem de erro."""
    return _RUNTIME_PATH_RE.sub("<runtime>", message).strip()


def _classify(message: str) -> ErrorCode:
    """Classifica a mensagem do motor num `ErrorCode` acionável."""
    lowered = message.casefold()
    if any(marker in lowered for marker in _INVALID_FILE_MARKERS):
        return ErrorCode.HYPER_INVALID_FILE
    return ErrorCode.HYPER_SQL_ERROR


def _translate(exc: Exception) -> HyperEngineError:
    """Traduz uma `HyperException` para `HyperEngineError` (código + mensagem).

    Preserva a `main_message` do motor (RF15), mas remove paths internos do
    runtime; exceções inesperadas viram um `HYPER_SQL_ERROR` genérico.
    """
    raw = getattr(exc, "main_message", None) or str(exc)
    message = _scrub_runtime_paths(raw)
    if not message:
        message = "Falha no motor Hyper ao processar a operação."
    return HyperEngineError(_classify(message), message)

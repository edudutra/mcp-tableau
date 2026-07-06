"""Extração de bancos externos para `.hyper` via SQLAlchemy Core (RF9–RF12).

Módulo isolado que fala com bancos externos (somente leitura) e materializa o
resultado num extrato `.hyper`. Análogo a `hyper/engine.py` para o runtime local:
concentra toda a superfície de erro externa (rede, autenticação, SQL) e a
tradução para `ErrorCode` acionáveis.

Princípios inegociáveis:

- **Credenciais só do ambiente** (RF11): a connection string vem exclusivamente
  de `HYPER_DB_CONN_<NOME>`, resolvida por :func:`resolve_connection` lendo
  `os.environ` diretamente — desvio pontual e documentado do padrão `Settings`,
  pois `pydantic-settings` não modela chaves dinâmicas (decisão 2 da techspec). A
  URL resolvida **nunca** é logada nem incluída em exceções ou retornos.
- **Sanitização obrigatória** (RF11): toda mensagem de erro que sai do módulo
  passa por :func:`_sanitize`, que remove a URL e suas partes (usuário, senha,
  host) antes de virar `DbError.message`.
- **Streaming** (RF9): a query é executada com `stream_results=True` e o cursor é
  lido em lotes de 10.000 linhas, gravados incrementalmente via `Inserter` — sem
  carregar o resultado inteiro em memória.
- **Classificação de erros** (RF12): falha de rede → `DB_CONNECTION_FAILED`,
  credencial recusada → `DB_AUTH_FAILED`, SQL rejeitado → `DB_QUERY_ERROR`.

Como em `engine.py`, o import do runtime Hyper é tolerante à ausência da
biblioteca (`hapi is None`) para viabilizar a suíte rápida/CI sem o binário
pesado; os testes injetam um módulo falso em ``hapi``.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import (
    DatabaseError,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)

from mcp_tableau.hyper.engine import EXTRACT_SCHEMA
from mcp_tableau.models import ErrorCode, HyperColumn

try:  # pragma: no cover - depende do runtime instalado
    import tableauhyperapi as hapi
except ImportError:  # pragma: no cover - runtime ausente na suíte rápida/CI
    hapi = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Prefixo das variáveis de ambiente de conexão nomeada (RF9, decisão 2).
_CONN_PREFIX = "HYPER_DB_CONN_"

# Lote de leitura do cursor (RF9): 10.000 linhas por `fetchmany`.
_DEFAULT_BATCH_SIZE = 10_000

# Marcadores de autenticação nas mensagens dos drivers (RF12). Heurística
# multi-dialeto: a categoria de auth precede o fallback de conexão.
_AUTH_MARKERS = (
    "authentication",
    "auth failed",
    "access denied",
    "login failed",
    "password",
    "not authorized",
    "permission denied",
    "role does not exist",
)

# Token genérico de connection string (`esquema://credenciais@host/base`); rede
# de segurança da sanitização quando o driver ecoa a URL bruta.
_URL_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://\S+")


class DbError(Exception):
    """Erro de banco externo já traduzido para um `ErrorCode` acionável.

    A `message` é sempre sanitizada (sem URL/usuário/senha/host) antes de ser
    construída — pode ser propagada direto ao `ToolError`.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DbConfigError(DbError):
    """Conexão nomeada não configurada no ambiente (`DB_CONNECTION_NOT_CONFIGURED`).

    Cita apenas o nome lógico e o nome da variável esperada — jamais uma URL.
    """


@dataclass(slots=True)
class ExtractReport:
    """Resultado de uma extração concluída, pronto para montar `HyperCreateResult`.

    `warnings` acumula avisos não bloqueantes do próprio módulo (ex.: tipo de
    origem exótico mapeado para `text`); o alerta de volume pós-extração é
    adicionado pela tool.
    """

    columns: list[HyperColumn] = field(default_factory=list)
    row_count: int = 0
    warnings: list[str] = field(default_factory=list)


def resolve_connection(name: str) -> str:
    """Resolve o nome lógico para a connection string em `HYPER_DB_CONN_<NAME>`.

    O nome é normalizado para maiúsculas e concatenado ao prefixo. Ausente a
    variável, levanta `DbConfigError` citando **o nome da variável** (nunca uma
    URL). A URL resolvida não é logada nem incluída em nenhuma exceção.

    Args:
        name: Nome lógico da conexão (ex.: ``"VENDAS"``).

    Returns:
        A connection string (URL SQLAlchemy) lida do ambiente.

    Raises:
        DbConfigError: quando a variável de ambiente correspondente está ausente.
    """
    var_name = f"{_CONN_PREFIX}{name.upper()}"
    url = os.environ.get(var_name)
    if not url:
        raise DbConfigError(
            ErrorCode.DB_CONNECTION_NOT_CONFIGURED,
            f"Conexão '{name}' não configurada. Defina a variável de ambiente "
            f"{var_name} no host do servidor MCP.",
        )
    return url


def extract_to_hyper(
    connection_name: str,
    query: str,
    hyper_path: Path,
    table_name: str,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> ExtractReport:
    """Executa `query` no banco nomeado e materializa o resultado em `.hyper`.

    Abre o engine SQLAlchemy com `pool_pre_ping=True`, executa a consulta com
    `stream_results=True` e lê o cursor em lotes de `batch_size`, gravando cada
    lote via `Inserter`. O schema da tabela é derivado dos tipos das primeiras
    linhas, com fallback para `text` (com aviso) em tipos exóticos. Um resultado
    vazio cria o `.hyper` com zero linhas, sem erro.

    Args:
        connection_name: Nome lógico resolvido por :func:`resolve_connection`.
        query: SQL executado na origem (aberto em leitura; nenhum write é emitido).
        hyper_path: Destino `.hyper`.
        table_name: Tabela de destino no schema `Extract`.
        batch_size: Tamanho do lote de leitura/gravação.

    Returns:
        `ExtractReport` com colunas efetivas, total de linhas e avisos.

    Raises:
        DbError: falha de conexão, autenticação ou SQL, sempre com mensagem
            sanitizada (sem URL/credencial).
        DbConfigError: conexão não configurada (via :func:`resolve_connection`).
    """
    url = resolve_connection(connection_name)
    _require_runtime()

    engine = None
    try:
        engine = create_engine(url, pool_pre_ping=True)
        # Somente leitura: apenas a `query` (SELECT) é emitida e a conexão é
        # fechada sem commit. `stream_results=True` evita materializar tudo.
        with engine.connect() as raw_conn:
            conn = raw_conn.execution_options(stream_results=True)
            result = conn.execute(text(query))
            column_names = list(result.keys())
            first_batch = [list(row) for row in result.fetchmany(batch_size)]
            columns, sql_types, coercers, warnings = _infer_schema(
                column_names, first_batch
            )
            row_count = _write_hyper(
                hyper_path,
                table_name,
                columns,
                sql_types,
                coercers,
                first_batch,
                result,
                batch_size,
            )
    except SQLAlchemyError as exc:
        raise _translate_db_error(exc, url) from None
    finally:
        if engine is not None:
            engine.dispose()

    return ExtractReport(columns=columns, row_count=row_count, warnings=warnings)


# -- Inferência de schema (cursor → SqlType) -----------------------------------


def _infer_schema(
    names: Sequence[str], sample_rows: Sequence[Sequence[object]]
) -> tuple[
    list[HyperColumn], list[object], dict[int, Callable[[object], object]], list[str]
]:
    """Deriva colunas/`SqlType` dos tipos das primeiras linhas (fallback `text`).

    Amostra o primeiro valor não nulo de cada coluna. Tipos exóticos (fora do
    mapa) viram `text` com um aviso e uma coerção `str()`; `double` recebe
    coerção `float()` para aceitar `Decimal`/`int` na inserção.

    Returns:
        `(colunas, sql_types, coercers, warnings)`, onde `coercers` mapeia o
        índice da coluna à função aplicada a cada valor antes da gravação.
    """
    columns: list[HyperColumn] = []
    sql_types: list[object] = []
    coercers: dict[int, Callable[[object], object]] = {}
    warnings: list[str] = []

    for index, name in enumerate(names):
        sample = _first_non_null(sample_rows, index)
        contract, sql_type, coercer, exotic = _map_value(sample)
        if exotic:
            warnings.append(
                f"Coluna '{name}': tipo de origem não mapeado; convertido para text."
            )
        if coercer is not None:
            coercers[index] = coercer
        columns.append(HyperColumn(name=str(name), type=contract, nullable=True))
        sql_types.append(sql_type)

    return columns, sql_types, coercers, warnings


def _first_non_null(rows: Sequence[Sequence[object]], index: int) -> object:
    """Primeiro valor não nulo da coluna `index` na amostra; `None` se não houver."""
    for row in rows:
        if index < len(row) and row[index] is not None:
            return row[index]
    return None


def _map_value(
    value: object,
) -> tuple[str, object, Callable[[object], object] | None, bool]:
    """Mapeia um valor de amostra para `(contrato, SqlType, coercer, exótico)`.

    `bool` precede `int` (é subclasse) e `datetime` precede `date` (idem). Colunas
    só-nulas ou de tipo desconhecido caem em `text`; desconhecido também sinaliza
    `exótico` (aviso + coerção `str()`).
    """
    if value is None:
        return "text", hapi.SqlType.text(), None, False
    if isinstance(value, bool):
        return "bool", hapi.SqlType.bool(), None, False
    if isinstance(value, int):
        return "big_int", hapi.SqlType.big_int(), None, False
    if isinstance(value, (float, Decimal)):
        return "double", hapi.SqlType.double(), _to_float, False
    if isinstance(value, str):
        return "text", hapi.SqlType.text(), None, False
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            return "timestamp_tz", hapi.SqlType.timestamp_tz(), None, False
        return "timestamp", hapi.SqlType.timestamp(), None, False
    if isinstance(value, datetime.date):
        return "date", hapi.SqlType.date(), None, False
    return "text", hapi.SqlType.text(), _to_str, True


def _to_float(value: object) -> object:
    """Coage a `float` (aceita `Decimal`/`int`); preserva `None`."""
    return None if value is None else float(value)  # type: ignore[arg-type]


def _to_str(value: object) -> object:
    """Coage a `str` valores de tipo exótico; preserva `None`."""
    return None if value is None else str(value)


# -- Gravação no `.hyper` (Inserter em lotes) ----------------------------------


def _write_hyper(
    hyper_path: Path,
    table_name: str,
    columns: Sequence[HyperColumn],
    sql_types: Sequence[object],
    coercers: dict[int, Callable[[object], object]],
    first_batch: Sequence[Sequence[object]],
    result: object,
    batch_size: int,
) -> int:
    """Cria a tabela e insere o cursor em lotes via `Inserter`; retorna o total.

    O primeiro lote (já lido para inferir o schema) é gravado primeiro; os
    demais são drenados do cursor com `fetchmany(batch_size)`. Um único
    `Inserter` acumula os lotes e é executado uma vez no final.
    """
    definition = _table_definition(table_name, columns, sql_types)
    total = 0
    with hapi.HyperProcess(
        telemetry=hapi.Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU
    ) as process:
        with hapi.Connection(
            endpoint=process.endpoint,
            database=str(hyper_path),
            create_mode=hapi.CreateMode.CREATE_AND_REPLACE,
        ) as conn:
            conn.catalog.create_schema_if_not_exists(hapi.SchemaName(EXTRACT_SCHEMA))
            conn.catalog.create_table(definition)
            with hapi.Inserter(conn, definition) as inserter:
                total += _insert_batch(inserter, first_batch, coercers)
                while True:
                    batch = result.fetchmany(batch_size)
                    if not batch:
                        break
                    total += _insert_batch(inserter, batch, coercers)
                inserter.execute()
    return total


def _insert_batch(
    inserter: object,
    batch: Sequence[Sequence[object]],
    coercers: dict[int, Callable[[object], object]],
) -> int:
    """Aplica as coerções por coluna e adiciona o lote ao `Inserter`."""
    if not batch:
        return 0
    rows = [_coerce_row(row, coercers) for row in batch] if coercers else batch
    inserter.add_rows(rows)
    return len(batch)


def _coerce_row(
    row: Sequence[object], coercers: dict[int, Callable[[object], object]]
) -> list[object]:
    """Aplica os coercers registrados às colunas correspondentes da linha."""
    coerced = list(row)
    for index, coercer in coercers.items():
        if index < len(coerced):
            coerced[index] = coercer(coerced[index])
    return coerced


def _table_definition(
    table_name: str, columns: Sequence[HyperColumn], sql_types: Sequence[object]
) -> object:
    """Monta a `TableDefinition` qualificada em `Extract` com os `SqlType` dados."""
    cols = [
        hapi.TableDefinition.Column(col.name, sql_type, hapi.NULLABLE)
        for col, sql_type in zip(columns, sql_types, strict=True)
    ]
    return hapi.TableDefinition(hapi.TableName(EXTRACT_SCHEMA, table_name), cols)


def _require_runtime() -> None:
    """Garante que o runtime Hyper está disponível antes de gravar o extrato."""
    if hapi is None:
        raise DbError(
            ErrorCode.HYPER_SQL_ERROR,
            "Runtime Hyper (tableauhyperapi) não está instalado neste ambiente.",
        )


# -- Classificação e sanitização de erros (RF11–RF12) --------------------------


def _translate_db_error(exc: SQLAlchemyError, url: str) -> DbError:
    """Traduz uma exceção SQLAlchemy para `DbError` com mensagem sanitizada.

    `OperationalError` de rede vira `DB_CONNECTION_FAILED`, salvo quando a
    mensagem indica autenticação (`DB_AUTH_FAILED`); `ProgrammingError`/
    `DatabaseError` viram `DB_QUERY_ERROR`; o restante cai em
    `DB_CONNECTION_FAILED`. A mensagem original é sempre sanitizada antes de sair.
    """
    raw = str(getattr(exc, "orig", None) or exc)
    message = _sanitize(raw, url)
    if not message:
        message = "Falha ao acessar o banco de origem."

    if isinstance(exc, OperationalError):
        if _looks_like_auth(raw):
            return DbError(ErrorCode.DB_AUTH_FAILED, message)
        return DbError(ErrorCode.DB_CONNECTION_FAILED, message)
    if isinstance(exc, (ProgrammingError, DatabaseError)):
        return DbError(ErrorCode.DB_QUERY_ERROR, message)
    return DbError(ErrorCode.DB_CONNECTION_FAILED, message)


def _looks_like_auth(message: str) -> bool:
    """Heurística multi-dialeto: a mensagem sugere falha de autenticação?"""
    lowered = message.casefold()
    return any(marker in lowered for marker in _AUTH_MARKERS)


def _sanitize(message: str, url: str | None) -> str:
    """Remove a URL e suas partes (usuário, senha, host) de uma mensagem (RF11).

    Substitui ocorrências literais dos componentes da connection string por
    ``<redacted>`` e, como rede de segurança, apaga qualquer token no formato
    ``esquema://...`` que reste na mensagem (drivers às vezes ecoam a URL bruta).
    """
    sanitized = message
    for part in _url_parts(url):
        sanitized = sanitized.replace(part, "<redacted>")
    sanitized = _URL_TOKEN_RE.sub("<redacted>", sanitized)
    return sanitized.strip()


def _url_parts(url: str | None) -> list[str]:
    """Extrai os fragmentos sensíveis de uma URL para remoção literal.

    Inclui a URL inteira, o render sem query e cada componente
    (usuário/senha/host/porta/database). Falha de parsing degrada para remover ao
    menos a string bruta da URL.
    """
    if not url:
        return []
    parts: list[str] = [url]
    try:
        parsed = make_url(url)
    except Exception:  # noqa: BLE001 - URL malformada: remove ao menos a bruta
        return parts
    parts.append(parsed.render_as_string(hide_password=False))
    for component in (
        parsed.username,
        parsed.password,
        parsed.host,
        parsed.database,
    ):
        if component:
            parts.append(str(component))
    if parsed.port is not None:
        parts.append(str(parsed.port))
    # Remove os mais longos primeiro para não deixar fragmentos órfãos.
    return sorted({part for part in parts if part}, key=len, reverse=True)

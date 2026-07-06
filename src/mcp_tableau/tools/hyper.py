"""Ferramentas MCP da Capacidade 5 (Hyper Datasources): ciclo de vida de `.hyper`.

Camada MCP fina sobre o motor local (`hyper/engine.py`) e a extração de bancos
externos (`hyper/db.py`). Cada tool valida a entrada **antes** de abrir uma
sessão Hyper (nenhuma operação de motor em erro local), delega a lógica pesada ao
engine/validações puras e monta o contrato de retorno tipado. Erros do motor
chegam como `HyperEngineError` (já com `ErrorCode`) e viram o envelope
`ToolError`; salvaguardas de volume produzem `VolumeAlert` (pré-execução, sem
confirmação) ou `warnings` (execução confirmada).

O registro no servidor FastMCP é feito por `register(mcp)`, chamado por
`server.py` — sem acoplar ao singleton.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

from mcp_tableau.config import load_settings
from mcp_tableau.hyper import db
from mcp_tableau.hyper.engine import (
    AppendRequest,
    FileIngestRequest,
    HyperEngineError,
    InlineIngestRequest,
    hyper_session,
)
from mcp_tableau.models import (
    ErrorCode,
    ExceededDimension,
    HyperCreateResult,
    HyperMutationResult,
    HyperQueryResult,
    HyperSchemaReport,
    HyperTableInfo,
    InlineColumn,
    ToolError,
    VolumeAlert,
)
from mcp_tableau.validation.volume import (
    check_extracted_rows,
    check_inline_rows,
    check_source_file,
)

# Extensão obrigatória de um extrato Hyper.
_HYPER_SUFFIX = ".hyper"

# Guarda de leitura de `query_hyper`: primeira palavra-chave admitida (RF13).
_READ_KEYWORDS = frozenset({"SELECT", "WITH"})

# Teto rígido de linhas retornadas por consulta (RF14); o default vem de Settings.
_MAX_ROWS_CEILING = 10_000

# Extensão de arquivo de origem → formato de ingestão (modo `auto`).
_SOURCE_SUFFIX_FORMAT = {".csv": "csv", ".parquet": "parquet"}

# Palavra-chave inicial de `execute_hyper_sql` → rótulo de operação (RF19–RF20).
_WRITE_OPERATIONS: dict[str, str] = {
    "INSERT": "insert",
    "UPDATE": "update",
    "DELETE": "delete",
    "CREATE": "create_table_as",
}

# Marcadores de "tabela inexistente" na mensagem do motor → traduzidos p/ NOT_FOUND.
_NOT_FOUND_MARKERS = (
    "does not exist",
    "não existe",
    "no such table",
    "unknown table",
    "not found",
)


def inspect_hyper_schema(hyper_path: str) -> HyperSchemaReport | ToolError:
    """Inspeciona a estrutura completa de um arquivo `.hyper` local.

    Análogo local de `inspect_workbook_structure`: lista todos os schemas e
    tabelas do arquivo com colunas (nome, tipo lógico e nulabilidade) e a
    contagem de linhas por tabela. A contagem de uma tabela específica que falhe
    vira `null` (campo presente), sem abortar o relatório — a inspeção é
    tolerante a tabelas problemáticas.

    Args:
        hyper_path: Caminho local do arquivo `.hyper` a inspecionar.

    Returns:
        `HyperSchemaReport` em caso de sucesso, ou `ToolError` com
        `HYPER_INVALID_FILE` quando o caminho não aponta para um `.hyper` válido
        (extensão errada, arquivo inexistente ou não abrível pelo motor Hyper).
    """
    path = Path(hyper_path)
    invalid = _require_hyper_file(path)
    if invalid is not None:
        return invalid

    try:
        with hyper_session() as engine:
            reports = engine.describe(path)
    except HyperEngineError as exc:
        return ToolError.of(exc.code, exc.message)

    tables = [
        HyperTableInfo(
            schema_name=report.schema_name,
            table_name=report.table_name,
            columns=report.columns,
            row_count=report.row_count,
        )
        for report in reports
    ]
    return HyperSchemaReport(
        hyper_path=str(path),
        file_size_bytes=path.stat().st_size,
        tables=tables,
    )


def query_hyper(
    hyper_path: str, query: str, max_rows: int | None = None
) -> HyperQueryResult | ToolError:
    """Executa uma consulta SQL **de leitura** sobre um `.hyper` local.

    Guarda de leitura (ergonomia, não segurança): a primeira palavra-chave do
    comando deve ser `SELECT` ou `WITH`; um comando de escrita é recusado com
    `VALIDATION_ERROR` orientando o uso de `execute_hyper_sql`.

    O resultado é truncado em `max_rows` (default `HYPER_MAX_RESULT_ROWS`, faixa
    1–10.000): quando há mais linhas, `truncated=true` e o resultado nunca estoura
    o contexto do agente — refine com `LIMIT` ou agregações. Um resultado sem
    linhas **não é erro**: retorna `rows=[]` com `status="success"`. Datas e
    timestamps chegam como ISO-8601 e `numeric` como `str` (precisão preservada).

    Args:
        hyper_path: Caminho local de um `.hyper` existente e válido.
        query: Consulta `SELECT`/`WITH`.
        max_rows: Limite de linhas retornadas (1–10.000). Ausente usa o default
            de `HYPER_MAX_RESULT_ROWS`.

    Returns:
        `HyperQueryResult` em caso de sucesso, ou `ToolError`
        (`HYPER_INVALID_FILE` para arquivo inválido, `HYPER_SQL_ERROR` para SQL
        rejeitado pelo motor — com a mensagem original —, `VALIDATION_ERROR` para
        comando de escrita ou `max_rows` fora da faixa).
    """
    path = Path(hyper_path)
    invalid = _require_hyper_file(path)
    if invalid is not None:
        return invalid

    if _first_keyword(query) not in _READ_KEYWORDS:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            "query_hyper aceita apenas leitura (SELECT/WITH). Para INSERT, "
            "UPDATE, DELETE ou CREATE TABLE AS, use execute_hyper_sql.",
        )

    settings = load_settings()
    effective_max = settings.hyper_max_result_rows if max_rows is None else max_rows
    if effective_max < 1 or effective_max > _MAX_ROWS_CEILING:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"max_rows deve estar entre 1 e {_MAX_ROWS_CEILING}; recebido {max_rows}.",
        )

    try:
        with hyper_session() as engine:
            result = engine.query(path, query, effective_max)
    except HyperEngineError as exc:
        return ToolError.of(exc.code, exc.message)

    return HyperQueryResult(
        columns=result.columns,
        rows=result.rows,
        row_count=len(result.rows),
        truncated=result.truncated,
        max_rows=effective_max,
    )


def create_hyper_from_file(
    source_path: str,
    hyper_path: str,
    table_name: str = "Extract",
    source_format: Literal["auto", "csv", "parquet"] = "auto",
    delimiter: str = ",",
    encoding: str = "utf-8",
    header: bool = True,
    schema: list[InlineColumn] | None = None,
    confirm_large_operation: bool = False,
) -> HyperCreateResult | VolumeAlert | ToolError:
    """Cria um `.hyper` a partir de um arquivo CSV ou Parquet local.

    Sem `schema`, o motor infere as colunas (`external()`); com `schema`, cria a
    definição explícita e carrega via `COPY FROM` — dando controle total de tipos
    e erros mais claros. A tabela é criada no schema `Extract` (compatibilidade
    com Tableau Server antigos) e o arquivo de destino é sobrescrito se existir.

    Salvaguarda de volume (RF23–RF24): quando o arquivo de origem excede
    `HYPER_MAX_SOURCE_FILE_MB` e `confirm_large_operation=false`, a operação
    **não é executada** e retorna um `VolumeAlert` — repita com
    `confirm_large_operation=true` após confirmar com o usuário. Executada com
    confirmação, o alerta é replicado em `warnings` (rastro auditável).

    Args:
        source_path: Caminho local do arquivo `.csv`/`.parquet` de origem.
        hyper_path: Destino `.hyper` (diretório-pai deve existir).
        table_name: Nome da tabela criada (schema `Extract`).
        source_format: `auto` (pela extensão), `csv` ou `parquet`.
        delimiter: Delimitador do CSV (1 caractere).
        encoding: Encoding do CSV.
        header: Se o CSV tem linha de cabeçalho.
        schema: Colunas explícitas; ausente ativa a inferência (RF3).
        confirm_large_operation: Confirma execução acima do limiar de volume.

    Returns:
        `HyperCreateResult` em caso de sucesso, `VolumeAlert` quando acima do
        limiar sem confirmação, ou `ToolError` (`INVALID_FILE` para origem
        inexistente/formato desconhecido, `HYPER_SCHEMA_MISMATCH` para schema
        incompatível, `HYPER_SQL_ERROR` para falha do motor, `VALIDATION_ERROR`
        para destino inválido).
    """
    src = Path(source_path)
    if not src.is_file():
        return ToolError.of(
            ErrorCode.INVALID_FILE,
            f"Arquivo de origem não encontrado: '{source_path}'.",
        )
    resolved = _resolve_source_format(src, source_format)
    if resolved is None:
        return ToolError.of(
            ErrorCode.INVALID_FILE,
            f"Formato de origem indeterminado para '{src.name}'. Use uma "
            "extensão .csv/.parquet ou informe source_format explicitamente.",
        )

    dest = Path(hyper_path)
    invalid = _require_hyper_destination(dest)
    if invalid is not None:
        return invalid

    settings = load_settings()
    exceeded = check_source_file(src, settings)
    if exceeded and not confirm_large_operation:
        return _volume_alert(exceeded)

    request = FileIngestRequest(
        source_path=src,
        hyper_path=dest,
        table_name=table_name,
        source_format=resolved,
        delimiter=delimiter,
        encoding=encoding,
        header=header,
        schema=schema,
    )
    try:
        with hyper_session() as engine:
            report = engine.create_table_from_file(request)
    except HyperEngineError as exc:
        return ToolError.of(exc.code, exc.message)

    return HyperCreateResult(
        hyper_path=str(dest),
        table_name=report.table_name,
        columns=report.columns,
        row_count=report.row_count if report.row_count is not None else 0,
        source=resolved,
        warnings=[_describe_dimension(dim) for dim in exceeded],
    )


def create_hyper_from_inline(
    hyper_path: str,
    table_name: str,
    columns: list[InlineColumn],
    rows: list[list[object]],
    confirm_large_operation: bool = False,
) -> HyperCreateResult | VolumeAlert | ToolError:
    """Cria um `.hyper` a partir de colunas e linhas enviadas na própria chamada.

    Indicada para de-paras e tabelas de referência pequenas. Acima de
    `HYPER_MAX_INLINE_ROWS`, prefira `create_hyper_from_file` (a docstring e o
    `VolumeAlert` orientam essa escolha — RF8).

    Validação **tudo-ou-nada**: qualquer linha com aridade incorreta ou valor não
    coercível ao tipo declarado aborta a operação **antes de tocar o arquivo**,
    com mensagem citando a linha e a coluna ofensora (`HYPER_SCHEMA_MISMATCH`).
    Datas/timestamps são aceitos em ISO-8601. Acima do limiar de volume sem
    `confirm_large_operation=true`, retorna `VolumeAlert` sem executar.

    Args:
        hyper_path: Destino `.hyper` (diretório-pai deve existir).
        table_name: Nome da tabela criada (schema `Extract`).
        columns: Definição das colunas (≥ 1, nomes únicos).
        rows: Linhas com a aridade de `columns`; valores coercíveis aos tipos.
        confirm_large_operation: Confirma execução acima do limiar de volume.

    Returns:
        `HyperCreateResult` (`source="inline"`) em caso de sucesso, `VolumeAlert`
        acima do limiar sem confirmação, ou `ToolError` (`HYPER_SCHEMA_MISMATCH`
        para linha/valor inconsistente, `VALIDATION_ERROR` para `columns` vazio,
        nomes duplicados ou destino inválido).
    """
    dest = Path(hyper_path)
    invalid = _require_hyper_destination(dest)
    if invalid is not None:
        return invalid

    columns_error = _validate_columns(columns)
    if columns_error is not None:
        return columns_error

    coerced, mismatch = _coerce_rows(columns, rows)
    if mismatch is not None:
        return ToolError.of(ErrorCode.HYPER_SCHEMA_MISMATCH, mismatch)

    settings = load_settings()
    exceeded = check_inline_rows(len(rows), settings)
    if exceeded and not confirm_large_operation:
        return _volume_alert(exceeded)

    request = InlineIngestRequest(
        hyper_path=dest,
        table_name=table_name,
        columns=columns,
        rows=coerced,
    )
    try:
        with hyper_session() as engine:
            report = engine.create_table_from_rows(request)
    except HyperEngineError as exc:
        return ToolError.of(exc.code, exc.message)

    return HyperCreateResult(
        hyper_path=str(dest),
        table_name=report.table_name,
        columns=report.columns,
        row_count=report.row_count if report.row_count is not None else len(coerced),
        source="inline",
        warnings=[_describe_dimension(dim) for dim in exceeded],
    )


def extract_database_to_hyper(
    connection_name: str,
    query: str,
    hyper_path: str,
    table_name: str = "Extract",
) -> HyperCreateResult | ToolError:
    """Extrai o resultado de uma query de um banco externo para um `.hyper`.

    A conexão é referenciada **apenas** pelo nome lógico: a connection string vem
    exclusivamente da variável de ambiente `HYPER_DB_CONN_<NOME>` (uppercase) do
    host do servidor MCP — credenciais nunca são parâmetro, nem aparecem em logs,
    mensagens de erro ou no retorno (RF11). Um `connection_name` contendo `://`
    (indício de URL) é recusado com `VALIDATION_ERROR`.

    A query é executada em leitura na origem e o resultado é materializado em
    streaming (lotes de 10.000 linhas) na tabela `table_name` do schema `Extract`.
    Os tipos das colunas são derivados dos tipos do cursor, com fallback para
    `text` (registrado em `warnings`) em tipos exóticos. Um resultado vazio cria o
    `.hyper` com zero linhas, sem erro.

    Salvaguarda de volume (RF23/RF25): o volume não é estimável antes da execução;
    quando as linhas extraídas excedem `HYPER_MAX_EXTRACT_ROWS`, a extração
    **conclui normalmente** e o alerta é adicionado a `warnings` (pós-execução,
    sem bloqueio nem confirmação).

    Args:
        connection_name: Nome lógico da conexão (resolvido para
            `HYPER_DB_CONN_<NOME>`); nunca uma URL.
        query: SQL de leitura executado na origem.
        hyper_path: Destino `.hyper` (diretório-pai deve existir).
        table_name: Nome da tabela criada (schema `Extract`).

    Returns:
        `HyperCreateResult` (`source="database"`) em caso de sucesso, ou
        `ToolError` (`VALIDATION_ERROR` para `connection_name` com URL ou destino
        inválido, `DB_CONNECTION_NOT_CONFIGURED` para conexão ausente,
        `DB_CONNECTION_FAILED`/`DB_AUTH_FAILED`/`DB_QUERY_ERROR` para falhas da
        origem — sempre sem vazar a connection string).
    """
    if "://" in connection_name:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            "connection_name deve ser um nome lógico (ex.: 'VENDAS'), não uma "
            "URL. A connection string vem da variável de ambiente "
            "HYPER_DB_CONN_<NOME>.",
        )

    dest = Path(hyper_path)
    invalid = _require_hyper_destination(dest)
    if invalid is not None:
        return invalid

    try:
        report = db.extract_to_hyper(connection_name, query, dest, table_name)
    except db.DbError as exc:
        return ToolError.of(exc.code, exc.message)

    settings = load_settings()
    exceeded = check_extracted_rows(report.row_count, settings)
    warnings = report.warnings + [_describe_dimension(dim) for dim in exceeded]
    return HyperCreateResult(
        hyper_path=str(dest),
        table_name=_leaf_table_name(table_name),
        columns=report.columns,
        row_count=report.row_count,
        source="database",
        warnings=warnings,
    )


def append_to_hyper(
    hyper_path: str,
    table_name: str,
    source_path: str | None = None,
    columns: list[InlineColumn] | None = None,
    rows: list[list[object]] | None = None,
    confirm_large_operation: bool = False,
) -> HyperMutationResult | VolumeAlert | ToolError:
    """Acrescenta dados a uma tabela existente de um `.hyper`, de arquivo OU inline.

    Exatamente **uma** origem deve ser informada: `source_path` (CSV/Parquet) ou
    o par `columns`+`rows` (inline) — nenhuma ou ambas resultam em
    `VALIDATION_ERROR`. Na origem inline, a compatibilidade de schema com a
    tabela alvo (contagem, nomes e tipos base) é validada **antes de gravar**;
    incompatibilidade retorna `HYPER_SCHEMA_MISMATCH` sem gravar dado algum. A
    tabela pode ser qualificada (`schema.tabela`); ausente o schema, assume
    `Extract`.

    Salvaguardas de volume idênticas às de criação, sobre a origem correspondente
    (arquivo ou inline): acima do limiar sem `confirm_large_operation=true`,
    retorna `VolumeAlert` sem executar.

    Args:
        hyper_path: Caminho de um `.hyper` existente.
        table_name: Tabela alvo (schema `Extract` ou qualificada `schema.tabela`).
        source_path: Origem em arquivo `.csv`/`.parquet` (exclusivo com inline).
        columns: Colunas da origem inline (com `rows`).
        rows: Linhas da origem inline (com `columns`).
        confirm_large_operation: Confirma execução acima do limiar de volume.

    Returns:
        `HyperMutationResult` (`operation="append"`) em caso de sucesso,
        `VolumeAlert` acima do limiar sem confirmação, ou `ToolError`
        (`VALIDATION_ERROR` para origem ausente/ambígua, `HYPER_SCHEMA_MISMATCH`
        para divergência de schema, `NOT_FOUND` para tabela inexistente,
        `HYPER_INVALID_FILE`/`INVALID_FILE` para arquivos inválidos).
    """
    path = Path(hyper_path)
    invalid = _require_hyper_file(path)
    if invalid is not None:
        return invalid

    has_file = source_path is not None
    has_inline = columns is not None or rows is not None
    if has_file == has_inline:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            "Informe exatamente uma origem: source_path (arquivo) OU "
            "columns+rows (inline).",
        )

    settings = load_settings()
    if has_inline:
        return _append_inline(
            path, table_name, columns, rows, confirm_large_operation, settings
        )
    return _append_file(
        path, table_name, str(source_path), confirm_large_operation, settings
    )


def execute_hyper_sql(hyper_path: str, command: str) -> HyperMutationResult | ToolError:
    """Executa um comando SQL de **modificação** sobre um `.hyper` (RF19–RF20).

    Aceita um único comando por chamada cuja primeira palavra-chave seja `INSERT`,
    `UPDATE`, `DELETE` ou `CREATE` (para `CREATE TABLE ... AS`, derivando tabelas
    a partir de consultas). Comandos `SELECT`/`WITH` são recusados com
    `VALIDATION_ERROR` orientando o uso de `query_hyper`; qualquer outra
    palavra-chave (ex.: `DROP`) também é recusada.

    O `operation` do resultado é derivado da palavra-chave e `affected_rows` traz
    as linhas afetadas quando o motor as informa (`null` para DDL sem contagem).

    Args:
        hyper_path: Caminho de um `.hyper` existente.
        command: Um único comando de escrita SQL.

    Returns:
        `HyperMutationResult` em caso de sucesso, ou `ToolError`
        (`VALIDATION_ERROR` para palavra-chave não permitida, `HYPER_SQL_ERROR`
        para comando rejeitado pelo motor — com a mensagem original —,
        `HYPER_INVALID_FILE` para arquivo inválido).
    """
    path = Path(hyper_path)
    invalid = _require_hyper_file(path)
    if invalid is not None:
        return invalid

    keyword = _first_keyword(command)
    if keyword in _READ_KEYWORDS:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            "execute_hyper_sql não executa leitura. Para SELECT/WITH, use query_hyper.",
        )
    operation = _WRITE_OPERATIONS.get(keyword)
    if operation is None:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"Palavra-chave '{keyword or '(vazio)'}' não permitida em "
            "execute_hyper_sql. Use INSERT, UPDATE, DELETE ou CREATE TABLE AS.",
        )

    try:
        with hyper_session() as engine:
            affected = engine.execute(path, command)
    except HyperEngineError as exc:
        return ToolError.of(exc.code, exc.message)

    return HyperMutationResult(
        hyper_path=str(path),
        operation=operation,  # type: ignore[arg-type]
        affected_rows=affected,
        table_name=_parse_target_table(command, keyword),
        warnings=[],
    )


# -- Helpers compartilhados ----------------------------------------------------


def _require_hyper_file(path: Path) -> ToolError | None:
    """Valida que `path` é um `.hyper` existente; senão devolve `HYPER_INVALID_FILE`.

    Checagem local barata (extensão + existência) feita antes de abrir qualquer
    sessão Hyper. Um arquivo `.hyper` legítimo porém corrompido é detectado
    depois, pelo próprio motor, e também traduzido para `HYPER_INVALID_FILE`.
    """
    if path.suffix.lower() != _HYPER_SUFFIX:
        return ToolError.of(
            ErrorCode.HYPER_INVALID_FILE,
            f"O arquivo '{path}' não é um arquivo .hyper válido. Use "
            "create_hyper_from_file para converter dados brutos em extrato.",
        )
    if not path.is_file():
        return ToolError.of(
            ErrorCode.HYPER_INVALID_FILE,
            f"Arquivo .hyper não encontrado: '{path}'.",
        )
    return None


def _first_keyword(sql: str) -> str:
    """Primeira palavra-chave de um comando SQL, em maiúsculas (heurística simples)."""
    stripped = sql.strip()
    if not stripped:
        return ""
    return stripped.split(None, 1)[0].upper()


def _require_hyper_destination(path: Path) -> ToolError | None:
    """Valida o destino `.hyper`: extensão correta e diretório-pai existente.

    Não exige que o arquivo já exista (ele é criado/sobrescrito). Destino
    inválido é erro de parâmetro (`VALIDATION_ERROR`), não de arquivo Hyper.
    """
    if path.suffix.lower() != _HYPER_SUFFIX:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"O destino '{path}' deve ter extensão .hyper.",
        )
    if not path.parent.is_dir():
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"O diretório de destino '{path.parent}' não existe.",
        )
    return None


def _resolve_source_format(path: Path, source_format: str) -> str | None:
    """Resolve o formato de ingestão; `None` quando indeterminável/ inválido."""
    if source_format == "auto":
        return _SOURCE_SUFFIX_FORMAT.get(path.suffix.lower())
    if source_format in ("csv", "parquet"):
        return source_format
    return None


def _validate_columns(columns: list[InlineColumn]) -> ToolError | None:
    """Valida colunas inline: ≥ 1 coluna e nomes únicos (tipos via `InlineColumn`)."""
    if not columns:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            "É necessário informar ao menos uma coluna.",
        )
    names = [col.name for col in columns]
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            f"Colunas com nomes duplicados: {', '.join(duplicated)}.",
        )
    return None


def _coerce_rows(
    columns: list[InlineColumn], rows: list[list[object]]
) -> tuple[list[list[object]], str | None]:
    """Valida e coage as linhas ao tipo de cada coluna (tudo-ou-nada).

    Retorna `(linhas_coercidas, None)` quando todas as linhas são válidas, ou
    `([], mensagem)` na primeira inconsistência — a mensagem cita a linha
    (1-based) e a coluna ofensora e afirma que nada foi gravado.
    """
    coerced: list[list[object]] = []
    for index, row in enumerate(rows, start=1):
        if len(row) != len(columns):
            return [], (
                f"Linha {index}: esperadas {len(columns)} coluna(s), "
                f"recebidas {len(row)}. Nenhum dado foi gravado."
            )
        coerced_row: list[object] = []
        for value, col in zip(row, columns, strict=True):
            try:
                coerced_row.append(_coerce_value(value, col))
            except _CoercionError as exc:
                return [], f"Linha {index}: {exc} Nenhum dado foi gravado."
        coerced.append(coerced_row)
    return coerced, None


class _CoercionError(Exception):
    """Falha de coerção de um valor inline ao tipo declarado da coluna."""


def _coerce_value(value: object, col: InlineColumn) -> object:
    """Coage um valor único ao tipo lógico da coluna; levanta `_CoercionError`."""
    if value is None:
        if col.nullable:
            return None
        raise _CoercionError(f"coluna '{col.name}' não aceita NULL.")

    base = col.type.split("(", 1)[0]
    try:
        if base == "text":
            return str(value)
        if base == "big_int":
            return _coerce_int(value)
        if base == "double":
            return float(value)  # type: ignore[arg-type]
        if base == "bool":
            return _coerce_bool(value)
        if base == "numeric":
            return Decimal(str(value))
        if base == "date":
            return _coerce_date(value)
        if base in ("timestamp", "timestamp_tz"):
            return _coerce_datetime(value)
    except (TypeError, ValueError, InvalidOperation):
        raise _CoercionError(
            f"valor {value!r} não é coercível para {col.type} na coluna '{col.name}'."
        ) from None
    # Tipo fora do contrato não deveria chegar aqui (InlineColumn valida).
    raise _CoercionError(f"tipo '{col.type}' não suportado na coluna '{col.name}'.")


def _coerce_int(value: object) -> int:
    """Inteiro estrito; rejeita `bool` (evita `True`→1 silencioso)."""
    if isinstance(value, bool):
        raise ValueError("bool não é big_int")
    return int(value)  # type: ignore[arg-type]


def _coerce_bool(value: object) -> bool:
    """Booleano a partir de `bool`, inteiro 0/1 ou string true/false/0/1."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "0", "1"):
        return value.strip().lower() in ("true", "1")
    raise ValueError("valor não é booleano")


def _coerce_date(value: object) -> datetime.date:
    """Data a partir de `date`/`datetime` ou string ISO-8601."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        return datetime.date.fromisoformat(value)
    raise ValueError("valor não é data")


def _coerce_datetime(value: object) -> datetime.datetime:
    """Timestamp a partir de `datetime` ou string ISO-8601."""
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str):
        return datetime.datetime.fromisoformat(value)
    raise ValueError("valor não é timestamp")


def _append_inline(
    path: Path,
    table_name: str,
    columns: list[InlineColumn] | None,
    rows: list[list[object]] | None,
    confirm_large_operation: bool,
    settings: object,
) -> HyperMutationResult | VolumeAlert | ToolError:
    """Append de origem inline: valida colunas/linhas e delega ao engine."""
    if columns is None or rows is None:
        return ToolError.of(
            ErrorCode.VALIDATION_ERROR,
            "A origem inline exige columns e rows juntos.",
        )
    columns_error = _validate_columns(columns)
    if columns_error is not None:
        return columns_error
    coerced, mismatch = _coerce_rows(columns, rows)
    if mismatch is not None:
        return ToolError.of(ErrorCode.HYPER_SCHEMA_MISMATCH, mismatch)

    exceeded = check_inline_rows(len(rows), settings)  # type: ignore[arg-type]
    if exceeded and not confirm_large_operation:
        return _volume_alert(exceeded)

    request = AppendRequest(
        hyper_path=path, table_name=table_name, columns=columns, rows=coerced
    )
    try:
        with hyper_session() as engine:
            affected = engine.append_rows(request)
    except HyperEngineError as exc:
        return _map_engine_error(exc)

    return _append_result(path, table_name, affected, exceeded)


def _append_file(
    path: Path,
    table_name: str,
    source_path: str,
    confirm_large_operation: bool,
    settings: object,
) -> HyperMutationResult | VolumeAlert | ToolError:
    """Append de origem em arquivo: `INSERT ... SELECT * FROM external(...)`."""
    src = Path(source_path)
    if not src.is_file():
        return ToolError.of(
            ErrorCode.INVALID_FILE,
            f"Arquivo de origem não encontrado: '{source_path}'.",
        )
    resolved = _resolve_source_format(src, "auto")
    if resolved is None:
        return ToolError.of(
            ErrorCode.INVALID_FILE,
            f"Formato de origem indeterminado para '{src.name}'. Use uma "
            "extensão .csv/.parquet.",
        )

    exceeded = check_source_file(src, settings)  # type: ignore[arg-type]
    if exceeded and not confirm_large_operation:
        return _volume_alert(exceeded)

    command = _external_insert_sql(table_name, src, resolved)
    try:
        with hyper_session() as engine:
            affected = engine.execute(path, command)
    except HyperEngineError as exc:
        return _map_engine_error(exc)

    return _append_result(path, table_name, affected, exceeded)


def _append_result(
    path: Path,
    table_name: str,
    affected: int | None,
    exceeded: list[ExceededDimension],
) -> HyperMutationResult:
    """Monta o `HyperMutationResult` de um append concluído."""
    return HyperMutationResult(
        hyper_path=str(path),
        operation="append",
        affected_rows=affected,
        table_name=_leaf_table_name(table_name),
        warnings=[_describe_dimension(dim) for dim in exceeded],
    )


def _external_insert_sql(table_name: str, source: Path, source_format: str) -> str:
    """`INSERT INTO <tabela> SELECT * FROM external(<origem>)` (CSV/Parquet)."""
    path_literal = _sql_string_literal(str(source))
    if source_format == "parquet":
        external = f"external({path_literal})"
    else:
        external = (
            f"external({path_literal}, format => 'csv', "
            "delimiter => ',', header => true)"
        )
    return f"INSERT INTO {_qualified_table_ref(table_name)} SELECT * FROM {external}"


def _qualified_table_ref(table_name: str) -> str:
    """Referência qualificada e citada: `"Schema"."Tabela"` (schema default Extract)."""
    parts = [part.strip('"') for part in table_name.split(".", 1)]
    if len(parts) == 2:
        schema, table = parts
    else:
        schema, table = "Extract", parts[0]
    return f'"{schema}"."{table}"'


def _sql_string_literal(value: str) -> str:
    """Literal SQL de string com aspas simples internas escapadas (dobradas)."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _leaf_table_name(table_name: str) -> str:
    """Nome-folha da tabela (sem schema/aspas), para exibição no resultado."""
    return table_name.split(".")[-1].strip('"').strip()


def _parse_target_table(command: str, keyword: str) -> str | None:
    """Extrai o nome-folha da tabela alvo do comando (best-effort, sem parser SQL)."""
    tokens = command.replace("(", " ").split()
    upper = [token.upper() for token in tokens]
    try:
        if keyword == "CREATE":
            start = upper.index("TABLE") + 1
            if upper[start : start + 3] == ["IF", "NOT", "EXISTS"]:
                start += 3
            raw = tokens[start]
        elif keyword == "INSERT":
            raw = tokens[upper.index("INTO") + 1]
        elif keyword == "UPDATE":
            raw = tokens[1]
        elif keyword == "DELETE":
            raw = tokens[upper.index("FROM") + 1]
        else:
            return None
    except (ValueError, IndexError):
        return None
    return _leaf_table_name(raw)


def _map_engine_error(exc: HyperEngineError) -> ToolError:
    """Traduz `HyperEngineError`; "tabela inexistente" vira `NOT_FOUND` (RF18)."""
    if exc.code is ErrorCode.HYPER_SQL_ERROR and any(
        marker in exc.message.lower() for marker in _NOT_FOUND_MARKERS
    ):
        return ToolError.of(ErrorCode.NOT_FOUND, exc.message)
    return ToolError.of(exc.code, exc.message)


def _describe_dimension(dim: ExceededDimension) -> str:
    """Descrição em linguagem natural de uma dimensão de volume excedida."""
    return (
        f"Volume '{dim.dimension}' ({dim.actual}) excede o limiar "
        f"({dim.limit}). {dim.risk}"
    )


def _volume_alert(exceeded: list[ExceededDimension]) -> VolumeAlert:
    """Monta o `VolumeAlert` não bloqueante a partir das dimensões excedidas."""
    detail = " ".join(_describe_dimension(dim) for dim in exceeded)
    return VolumeAlert(
        exceeded=exceeded,
        message=f"{detail} A operação NÃO foi executada.",
        how_to_proceed=(
            "Confirme com o usuário e repita a chamada com "
            "confirm_large_operation=true para prosseguir."
        ),
    )


def register(mcp: FastMCP) -> None:
    """Registra as ferramentas de Hyper Datasources na instância FastMCP."""
    mcp.tool(inspect_hyper_schema)
    mcp.tool(query_hyper)
    mcp.tool(create_hyper_from_file)
    mcp.tool(create_hyper_from_inline)
    mcp.tool(extract_database_to_hyper)
    mcp.tool(append_to_hyper)
    mcp.tool(execute_hyper_sql)

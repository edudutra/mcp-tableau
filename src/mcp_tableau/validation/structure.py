"""Parsing estrutural puro de workbooks Tableau (`.twb`/`.twbx`).

`inspect_structure` extrai worksheets, dashboards, conexões, campos (com fórmula)
e filtros de um workbook usando `tableaudocumentapi`, e sinaliza problemas
estruturais (campo quebrado, filtro sem lógica, conexão inválida) como `issues`
sem falhar. XML corrompido ou arquivo inválido levanta `StructureParseError`,
um erro tratável que a camada de ferramentas converte em `ToolError`.

A função é pura: depende apenas do arquivo informado, sem rede nem TSC.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path


def _install_distutils_shim() -> None:
    """Registra um shim mínimo de `distutils.version.LooseVersion`.

    `tableaudocumentapi` importa `distutils.version.LooseVersion`, removido do
    Python a partir da 3.12. Como não podemos alterar a biblioteca de terceiros
    nem o ambiente, injetamos um substituto compatível em `sys.modules` antes do
    import. O efeito é local a este módulo e não altera o resto do pacote.
    """
    if "distutils.version" in sys.modules:
        return

    distutils_mod = sys.modules.get("distutils") or types.ModuleType("distutils")
    version_mod = types.ModuleType("distutils.version")

    class LooseVersion:
        """Comparador de versões frouxo, suficiente para o uso da biblioteca."""

        _component = re.compile(r"(\d+|[a-zA-Z]+)")

        def __init__(self, vstring: str | float | int) -> None:
            self.vstring = str(vstring)
            self.version = [
                int(part) if part.isdigit() else part
                for part in self._component.findall(self.vstring)
            ]

        def _key(self) -> tuple[tuple[int, object], ...]:
            # Inteiros ordenam depois de strings para evitar comparar tipos mistos.
            return tuple(
                (1, part) if isinstance(part, int) else (0, part)
                for part in self.version
            )

        def __lt__(self, other: object) -> bool:
            other = other if isinstance(other, LooseVersion) else LooseVersion(other)  # type: ignore[arg-type]
            return self._key() < other._key()

        def __eq__(self, other: object) -> bool:
            other = other if isinstance(other, LooseVersion) else LooseVersion(other)  # type: ignore[arg-type]
            return self._key() == other._key()

        def __le__(self, other: object) -> bool:
            return self < other or self == other

        def __repr__(self) -> str:
            return self.vstring

    version_mod.LooseVersion = LooseVersion  # type: ignore[attr-defined]
    distutils_mod.version = version_mod  # type: ignore[attr-defined]
    sys.modules.setdefault("distutils", distutils_mod)
    sys.modules["distutils.version"] = version_mod


_install_distutils_shim()

from tableaudocumentapi import Workbook  # noqa: E402
from tableaudocumentapi.xfile import (  # noqa: E402
    TableauInvalidFileException,
    TableauVersionNotSupportedException,
)

from mcp_tableau.models import (  # noqa: E402
    ConnectionInfo,
    FieldInfo,
    FilterInfo,
    StructureIssue,
    StructureReport,
)

# Extensões aceitas pela inspeção estrutural.
_VALID_SUFFIXES = frozenset({".twb", ".twbx"})

# Padrão de referência a campos dentro de uma fórmula calculada: [Nome do campo].
_FIELD_REFERENCE = re.compile(r"\[([^\[\]]+)\]")


class StructureParseError(Exception):
    """Erro tratável ao ler/parsear um workbook (arquivo inválido ou corrompido)."""


def inspect_structure(
    workbook_path: Path | str, workbook_id: str = ""
) -> StructureReport:
    """Inspeciona a estrutura interna de um workbook `.twb`/`.twbx`.

    Args:
        workbook_path: Caminho do arquivo de workbook (`.twb` ou `.twbx`).
        workbook_id: LUID do workbook quando conhecido. Como a inspeção opera
            sobre o arquivo local (que não carrega o LUID do servidor), o padrão
            é `""`; a ferramenta da Tarefa 7.0 preenche este campo ao publicar
            ou ao localizar o conteúdo no Tableau Server.

    Returns:
        `StructureReport` com worksheets, dashboards, conexões, campos, filtros e
        a lista de `issues` detectados (vazia quando nada de errado é encontrado).

    Raises:
        StructureParseError: Se o caminho for inválido, a extensão não for
            suportada, ou o XML estiver corrompido/ilegível.
    """
    path = Path(workbook_path)

    if path.suffix.lower() not in _VALID_SUFFIXES:
        raise StructureParseError(
            f"Extensão não suportada: '{path.suffix}'. Esperado '.twb' ou '.twbx'."
        )
    if not path.exists():
        raise StructureParseError(f"Arquivo de workbook não encontrado: '{path}'.")

    try:
        workbook = Workbook(str(path))
    except (
        TableauInvalidFileException,
        TableauVersionNotSupportedException,
    ) as exc:
        raise StructureParseError(
            f"Workbook inválido ou não suportado: '{path}'. Detalhe: {exc}"
        ) from exc
    except Exception as exc:  # XML corrompido eleva SyntaxError/lxml.XMLSyntaxError
        raise StructureParseError(
            f"Falha ao ler o workbook '{path}'. O arquivo pode estar corrompido. "
            f"Detalhe: {exc}"
        ) from exc

    worksheets = list(workbook.worksheets)
    dashboards = list(workbook.dashboards)

    connections, fields, defined_fields = _collect_datasources(workbook)
    filters = _collect_filters(path, worksheets)

    issues = _detect_issues(connections, fields, filters, defined_fields)

    return StructureReport(
        workbook_id=workbook_id,
        worksheets=worksheets,
        dashboards=dashboards,
        connections=connections,
        fields=fields,
        filters=filters,
        issues=issues,
    )


def _collect_datasources(
    workbook: Workbook,
) -> tuple[list[ConnectionInfo], list[FieldInfo], set[str]]:
    """Extrai conexões e campos das fontes de dados, e o conjunto de nomes válidos."""
    connections: list[ConnectionInfo] = []
    fields: list[FieldInfo] = []
    defined_fields: set[str] = set()

    for datasource in workbook.datasources:
        for connection in datasource.connections:
            conn_type = connection.dbclass or "unknown"
            server = connection.server or None
            connections.append(
                ConnectionInfo(
                    name=datasource.name or conn_type,
                    type=conn_type,
                    server=server,
                    is_valid=_is_connection_valid(conn_type, server),
                )
            )

        for field in datasource.fields.values():
            name = field.name or field.id or ""
            defined_fields.add(name)
            if field.id:
                defined_fields.add(field.id)
            fields.append(
                FieldInfo(
                    name=name,
                    datatype=field.datatype or "unknown",
                    role=field.role or "unknown",
                    is_calculated=field.calculation is not None,
                    formula=field.calculation,
                )
            )

    return connections, fields, defined_fields


def _is_connection_valid(conn_type: str, server: str | None) -> bool:
    """Heurística pura de validade da conexão.

    Conexões a banco (não locais, não embutidas) exigem servidor declarado; sua
    ausência indica conexão inválida/quebrada. Conexões de arquivo/extrato
    (`textscan`, `excel-direct`, `hyper`, `federated`, etc.) não precisam de
    servidor e são consideradas válidas.
    """
    if not conn_type or conn_type == "unknown":
        return False

    serverless = {
        "textscan",
        "excel-direct",
        "excel",
        "hyper",
        "dataengine",
        "federated",
        "msaccess",
        "spatial",
    }
    if conn_type.lower() in serverless:
        return True

    return bool(server)


def _collect_filters(path: Path, worksheets: list[str]) -> list[FilterInfo]:
    """Extrai filtros por worksheet diretamente do XML do workbook.

    `tableaudocumentapi` não expõe filtros, então lemos o XML cru. Um filtro
    "tem lógica" quando carrega alguma condição (faixa quantitativa, lista
    categórica, expressão de grupo); um filtro sem nenhuma condição é
    sinalizado como filtro sem lógica.
    """
    from lxml import etree as ET

    try:
        root = _open_workbook_xml(path)
    except Exception:
        # Filtros são complementares; se o XML não puder ser relido aqui,
        # devolvemos lista vazia em vez de quebrar a inspeção principal.
        return []

    filters: list[FilterInfo] = []
    for worksheet_el in root.findall(".//worksheets/worksheet"):
        worksheet_name = worksheet_el.attrib.get("name", "")
        for filter_el in worksheet_el.findall(".//filter"):
            column = filter_el.attrib.get("column", "")
            field = _field_from_column_ref(column)
            kind = filter_el.attrib.get("class", "unknown")
            filters.append(
                FilterInfo(
                    worksheet=worksheet_name,
                    field=field,
                    kind=kind,
                    has_logic=_filter_has_logic(filter_el, ET),
                )
            )

    return filters


def _open_workbook_xml(path: Path):
    """Retorna o elemento raiz do XML do workbook (`.twb` puro ou dentro do `.twbx`)."""
    import zipfile

    from lxml import etree as ET

    if zipfile.is_zipfile(str(path)):
        with zipfile.ZipFile(str(path)) as zf:
            inner = next(
                (n for n in zf.namelist() if n.lower().endswith(".twb")),
                None,
            )
            if inner is None:
                raise StructureParseError("Nenhum .twb encontrado no pacote .twbx.")
            with zf.open(inner) as handle:
                return ET.parse(handle).getroot()

    return ET.parse(str(path)).getroot()


def _filter_has_logic(filter_el, et_module) -> bool:
    """Decide se um filtro carrega alguma condição efetiva.

    Considera com lógica quando há elementos filhos que expressam restrição
    (groupfilter, min/max, etc.) ou quando há atributos de faixa explícitos.
    Um filtro completamente vazio (sem filhos e sem faixa) é tido como sem lógica.
    """
    children = [c for c in filter_el if not isinstance(c, et_module._Comment)]
    if children:
        return True

    range_attrs = ("included-values", "range", "from", "to")
    return any(attr in filter_el.attrib for attr in range_attrs)


def _field_from_column_ref(column: str) -> str:
    """Extrai o nome do campo de uma referência `[datasource].[Campo]`."""
    matches = _FIELD_REFERENCE.findall(column)
    if matches:
        return matches[-1]
    return column


def _detect_issues(
    connections: list[ConnectionInfo],
    fields: list[FieldInfo],
    filters: list[FilterInfo],
    defined_fields: set[str],
) -> list[StructureIssue]:
    """Constrói a lista de problemas estruturais sem falhar a inspeção."""
    issues: list[StructureIssue] = []

    # Conexões inválidas.
    for connection in connections:
        if not connection.is_valid:
            issues.append(
                StructureIssue(
                    code="invalid_connection",
                    severity="error",
                    target=connection.name,
                    detail=(
                        f"Conexão '{connection.name}' do tipo '{connection.type}' "
                        "parece inválida (servidor ausente ou tipo desconhecido)."
                    ),
                )
            )

    # Campos calculados referenciando campos inexistentes.
    for field in fields:
        if field.is_calculated and _has_broken_reference(field.formula, defined_fields):
            field.is_broken = True
            issues.append(
                StructureIssue(
                    code="broken_field",
                    severity="error",
                    target=field.name,
                    detail=(
                        f"Campo calculado '{field.name}' referencia um campo "
                        "inexistente em sua fórmula."
                    ),
                )
            )

    # Filtros sem lógica.
    for filter_info in filters:
        if not filter_info.has_logic:
            issues.append(
                StructureIssue(
                    code="filter_no_logic",
                    severity="warning",
                    target=f"{filter_info.worksheet}:{filter_info.field}",
                    detail=(
                        f"Filtro em '{filter_info.field}' na worksheet "
                        f"'{filter_info.worksheet}' não define nenhuma condição."
                    ),
                )
            )

    return issues


def _has_broken_reference(formula: str | None, defined_fields: set[str]) -> bool:
    """Indica se a fórmula referencia ao menos um campo não definido."""
    if not formula:
        return False

    referenced = _FIELD_REFERENCE.findall(formula)
    if not referenced:
        return False

    for ref in referenced:
        if ref in defined_fields:
            continue
        # Tolera referência com colchetes preservados, ex.: "[Vendas]".
        if f"[{ref}]" in defined_fields:
            continue
        return True

    return False

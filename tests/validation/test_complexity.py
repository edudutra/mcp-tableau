"""Testes da auditoria de complexidade pura (`validation/complexity.py`)."""

from __future__ import annotations

import pytest

from mcp_tableau.models import (
    ConnectionInfo,
    FieldInfo,
    FilterInfo,
    StructureReport,
    Thresholds,
)
from mcp_tableau.validation.complexity import audit_complexity


def _report(
    *,
    worksheets: int = 0,
    dashboards: int = 0,
    filters: int = 0,
    data_sources: int = 0,
    calculated: int = 0,
) -> StructureReport:
    """Constrói um `StructureReport` com as contagens desejadas."""
    return StructureReport(
        workbook_id="wb-1",
        worksheets=[f"ws{i}" for i in range(worksheets)],
        dashboards=[f"db{i}" for i in range(dashboards)],
        connections=[
            ConnectionInfo(name=f"c{i}", type="postgres", server="srv", is_valid=True)
            for i in range(data_sources)
        ],
        fields=[
            FieldInfo(
                name=f"calc{i}",
                datatype="real",
                role="measure",
                is_calculated=True,
                formula="[x]",
            )
            for i in range(calculated)
        ],
        filters=[
            FilterInfo(
                worksheet="ws0", field=f"f{i}", kind="categorical", has_logic=True
            )
            for i in range(filters)
        ],
    )


_DEFAULT_THRESHOLDS = Thresholds(max_filters=10, max_worksheets=20, max_data_sources=5)


def test_audit_complexity_dentro_dos_limiares_compliant_true() -> None:
    report = _report(worksheets=5, filters=3, data_sources=2)

    result = audit_complexity(report, _DEFAULT_THRESHOLDS)

    assert result.compliant is True
    assert result.findings == []
    assert result.metrics.worksheets == 5
    assert result.metrics.filters == 3
    assert result.metrics.data_sources == 2


def test_audit_complexity_excesso_de_filtros_gera_finding_warning() -> None:
    report = _report(filters=11)

    result = audit_complexity(report, _DEFAULT_THRESHOLDS)

    assert result.compliant is False
    findings = [f for f in result.findings if f.metric == "filters"]
    assert len(findings) == 1
    assert findings[0].value == 11
    assert findings[0].threshold == 10
    assert findings[0].severity == "warning"


def test_audit_complexity_excesso_de_worksheets_gera_finding() -> None:
    report = _report(worksheets=21)

    result = audit_complexity(report, _DEFAULT_THRESHOLDS)

    assert result.compliant is False
    assert any(f.metric == "worksheets" for f in result.findings)


def test_audit_complexity_multiplos_estouros_acumula_findings() -> None:
    report = _report(worksheets=21, filters=11, data_sources=6)

    result = audit_complexity(report, _DEFAULT_THRESHOLDS)

    metrics = {f.metric for f in result.findings}
    assert metrics == {"worksheets", "filters", "data_sources"}
    assert result.compliant is False


def test_audit_complexity_thresholds_customizados_alteram_resultado() -> None:
    report = _report(filters=4)

    # Sob limiar padrão (10) seria conforme; sob limiar 3, vira finding.
    permissivo = audit_complexity(
        report, Thresholds(max_filters=10, max_worksheets=20, max_data_sources=5)
    )
    restritivo = audit_complexity(
        report, Thresholds(max_filters=3, max_worksheets=20, max_data_sources=5)
    )

    assert permissivo.compliant is True
    assert restritivo.compliant is False
    assert any(f.metric == "filters" for f in restritivo.findings)


@pytest.mark.parametrize(
    ("worksheets", "filters", "data_sources"),
    [
        (20, 0, 0),  # worksheets no limite exato
        (0, 10, 0),  # filters no limite exato
        (0, 0, 5),  # data_sources no limite exato
    ],
)
def test_audit_complexity_valores_no_limite_exato_nao_geram_finding(
    worksheets: int, filters: int, data_sources: int
) -> None:
    report = _report(worksheets=worksheets, filters=filters, data_sources=data_sources)

    result = audit_complexity(report, _DEFAULT_THRESHOLDS)

    assert result.findings == []
    assert result.compliant is True

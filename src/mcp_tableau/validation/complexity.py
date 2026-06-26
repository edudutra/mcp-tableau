"""Auditoria pura de complexidade de workbook contra limiares de boas práticas.

`audit_complexity` deriva métricas de um `StructureReport`, compara cada uma com
o limiar correspondente e acumula `findings` para os excessos. Valores no limite
exato NÃO geram finding (comparação estrita com `>`). É pura: sem rede, sem TSC.
"""

from __future__ import annotations

from mcp_tableau.models import (
    ComplexityFinding,
    ComplexityMetrics,
    ComplexityReport,
    StructureReport,
    Thresholds,
)


def audit_complexity(
    report: StructureReport,
    thresholds: Thresholds,
    workbook_id: str = "",
) -> ComplexityReport:
    """Audita os indicadores de complexidade de um workbook contra limiares.

    Args:
        report: Relatório estrutural produzido por `inspect_structure`, fonte das
            contagens (worksheets, dashboards, filtros, fontes, calculados).
        thresholds: Limiares de boas práticas a comparar.
        workbook_id: LUID do workbook quando conhecido. Por padrão herda o
            `report.workbook_id`; a ferramenta da Tarefa 7.0 pode sobrescrever.

    Returns:
        `ComplexityReport` com métricas medidas, limiares aplicados, a lista de
        `findings` (um por limiar excedido) e `compliant=True` quando não há
        nenhum finding.

    Notes:
        Um valor exatamente igual ao limiar é considerado conforme — somente
        valores estritamente acima (`>`) geram finding.
    """
    metrics = _measure(report)

    findings: list[ComplexityFinding] = []
    _evaluate(
        findings,
        metric="filters",
        value=metrics.filters,
        threshold=thresholds.max_filters,
        recommendation=(
            "Reduza a quantidade de filtros ou consolide-os em parâmetros para "
            "diminuir o custo de renderização."
        ),
    )
    _evaluate(
        findings,
        metric="worksheets",
        value=metrics.worksheets,
        threshold=thresholds.max_worksheets,
        recommendation=(
            "Divida o workbook em vários menores; muitas worksheets pesam na "
            "carga e na manutenção."
        ),
    )
    _evaluate(
        findings,
        metric="data_sources",
        value=metrics.data_sources,
        threshold=thresholds.max_data_sources,
        recommendation=(
            "Consolide fontes de dados; muitas conexões aumentam a latência de "
            "atualização e o acoplamento."
        ),
    )

    return ComplexityReport(
        workbook_id=workbook_id or report.workbook_id,
        metrics=metrics,
        thresholds=thresholds,
        compliant=not findings,
        findings=findings,
    )


def _measure(report: StructureReport) -> ComplexityMetrics:
    """Deriva as contagens de complexidade a partir do relatório estrutural."""
    return ComplexityMetrics(
        worksheets=len(report.worksheets),
        dashboards=len(report.dashboards),
        filters=len(report.filters),
        data_sources=len(report.connections),
        calculated_fields=sum(1 for field in report.fields if field.is_calculated),
    )


def _evaluate(
    findings: list[ComplexityFinding],
    *,
    metric: str,
    value: int,
    threshold: int,
    recommendation: str,
) -> None:
    """Acrescenta um finding se `value` exceder estritamente `threshold`."""
    if value > threshold:
        findings.append(
            ComplexityFinding(
                metric=metric,
                value=value,
                threshold=threshold,
                severity="warning",
                recommendation=recommendation,
            )
        )

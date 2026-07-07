---
provider: manual
pr:
round: 1
round_created_at: 2026-07-07T14:27:08Z
status: resolved
file: tests/tools/test_visual.py
line: 0
severity: medium
author: claude-code
provider_ref:
---

# Issue 001: Missing test for TableauClientError in render_workbook_pdf

## Review Comment

The `render_workbook_pdf` function handles `TableauClientError` at lines 196-197 of `src/mcp_tableau/tools/visual.py`, but this exception path has no test coverage. The analogous `render_view_image` tool does have this test (`test_render_view_image_view_inexistente_retorna_not_found`), but no equivalent exists for the PDF tool.

This means the error-handling branch where the Tableau client raises `TableauClientError` (e.g., view not found, auth failed, permission denied) during PDF rendering is exercised only in production, never in tests. If a refactoring accidentally removed or broke this handler, the test suite would not catch it.

Suggested fix — add a test similar to:

```python
def test_render_workbook_pdf_view_inexistente_retorna_not_found(
    patched_session: MagicMock,
) -> None:
    patched_session.render_view_pdf.side_effect = TableauClientError(
        ErrorCode.NOT_FOUND, "Recurso não encontrado no Tableau."
    )

    result = visual.render_workbook_pdf("missing")

    assert isinstance(result, ToolError)
    assert result.error.code == ErrorCode.NOT_FOUND
```

## Triage

- Decision: `VALID`
- Notes: Confirmed. `render_workbook_pdf` (lines ~196-197 in `src/mcp_tableau/tools/visual.py`) catches `TableauClientError` and returns `ToolError.of(exc.code, exc.message)`. The analogous test exists for `render_view_image` (`test_render_view_image_view_inexistente_retorna_not_found`), but no equivalent covers the PDF tool. Adding a parallel test `test_render_workbook_pdf_view_inexistente_retorna_not_found` following the same pattern.

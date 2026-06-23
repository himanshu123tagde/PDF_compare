import html
from datetime import datetime


def _e(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _status_class(status: str) -> str:
    mapping = {
        "aligned": "status-aligned",
        "partial": "status-partial",
        "missing": "status-missing",
        "cannot_verify": "status-verify",
        "conflicting": "status-conflict",
        "compliant": "status-aligned",
        "non_compliant": "status-conflict",
        "undetermined": "status-verify",
    }
    return mapping.get(status, "status-neutral")


def _severity_class(severity: str) -> str:
    mapping = {"high": "severity-high", "medium": "severity-medium", "low": "severity-low"}
    return mapping.get(severity, "severity-medium")


def render_compliance_html(workflow: dict, result: dict, *, report_id: str, created_at: str) -> str:
    product = _e(workflow.get("product_name", "Product"))
    confidence = _e(result.get("assessment_confidence", "low"))
    level = _e(result.get("compliance_level", "undetermined"))
    score = result.get("overall_compliance_score")
    summary = _e(result.get("executive_summary", "No summary provided."))
    workflow_id = _e(workflow.get("id", ""))
    generated = _e(created_at or datetime.utcnow().isoformat())

    score_block = (
        f'<div class="metric-card"><span class="metric-label">Compliance Score</span>'
        f'<span class="metric-value">{_e(score)}/100</span></div>'
        if score is not None
        else '<div class="metric-card"><span class="metric-label">Compliance Score</span>'
        '<span class="metric-value muted">Not available</span>'
        '<span class="metric-note">Insufficient detailed evidence</span></div>'
    )

    sections: list[str] = []

    missing_evidence = result.get("missing_evidence") or []
    if missing_evidence:
        items = "".join(f"<li>{_e(item)}</li>" for item in missing_evidence)
        sections.append(
            f'<section><h2>Missing Evidence</h2><ul class="bullet-list">{items}</ul></section>'
        )

    requirements = result.get("gov_requirements") or []
    if requirements:
        rows = []
        for req in requirements:
            rows.append(
                "<tr>"
                f"<td>{_e(req.get('requirement_id', 'GR-?'))}</td>"
                f"<td>{_e(req.get('category', 'other'))}</td>"
                f"<td><span class='tag'>{_e(req.get('evidence_depth', 'unknown'))}</span></td>"
                f"<td>{_e(req.get('requirement_text', ''))}</td>"
                f"<td class='excerpt'>{_e(req.get('source_excerpt', ''))}</td>"
                "</tr>"
            )
        sections.append(
            "<section><h2>Government Requirements</h2>"
            "<table><thead><tr>"
            "<th>ID</th><th>Category</th><th>Depth</th><th>Requirement</th><th>Source Excerpt</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></section>"
        )

    alignments = result.get("alignments") or []
    if alignments:
        rows = []
        for item in alignments:
            status = item.get("status", "unknown")
            rows.append(
                "<tr>"
                f"<td>{_e(item.get('gov_requirement_id'))}</td>"
                f"<td>{_e(item.get('company_position_id') or '—')}</td>"
                f"<td><span class='badge {_status_class(status)}'>{_e(status)}</span></td>"
                f"<td>{_e(item.get('evidence', ''))}</td>"
                f"<td>{_e(item.get('gap_description') or '')}</td>"
                f"<td>{_e(item.get('recommended_action') or '')}</td>"
                "</tr>"
            )
        sections.append(
            "<section><h2>Requirement Alignments</h2>"
            "<table><thead><tr>"
            "<th>Gov ID</th><th>Company ID</th><th>Status</th>"
            "<th>Evidence</th><th>Gap</th><th>Recommended Action</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></section>"
        )

    gaps = result.get("coverage_gaps") or result.get("critical_gaps") or []
    if gaps:
        cards = []
        for gap in gaps:
            severity = gap.get("severity", "medium")
            cards.append(
                f'<article class="gap-card {_severity_class(severity)}">'
                f'<div class="gap-header">'
                f'<span class="badge {_severity_class(severity)}">{_e(severity).upper()}</span>'
                f'<span class="gap-type">{_e(gap.get("gap_type", "documentation_gap"))}</span>'
                f'<span class="gap-id">{_e(gap.get("gov_requirement_id", "GR-?"))}</span>'
                f"</div>"
                f'<p>{_e(gap.get("description", ""))}</p>'
                f'<p class="action"><strong>Action:</strong> {_e(gap.get("recommended_action", "—"))}</p>'
                f"</article>"
            )
        sections.append(
            "<section><h2>Coverage Gaps</h2>"
            + '<div class="card-grid">' + "".join(cards) + "</div></section>"
        )

    conflicts = result.get("conflicts") or []
    if conflicts:
        cards = []
        for conflict in conflicts:
            cards.append(
                '<article class="conflict-card">'
                f'<h3>{_e(conflict.get("gov_requirement_id", "GR-?"))}</h3>'
                f'<p>{_e(conflict.get("description", ""))}</p>'
                f'<blockquote><strong>Government:</strong> {_e(conflict.get("government_excerpt", ""))}</blockquote>'
                f'<blockquote><strong>Company:</strong> {_e(conflict.get("company_excerpt", ""))}</blockquote>'
                f'<p class="action"><strong>Action:</strong> {_e(conflict.get("recommended_action", "—"))}</p>'
                "</article>"
            )
        sections.append(
            "<section><h2>Confirmed Conflicts</h2>"
            + "".join(cards) + "</section>"
        )

    recommendations = result.get("recommendations") or []
    if recommendations:
        items = []
        for rec in sorted(recommendations, key=lambda r: r.get("priority", 99)):
            items.append(
                "<li>"
                f"<strong>#{_e(rec.get('priority', '-'))}</strong> {_e(rec.get('action', ''))}"
                f"<div class='subtext'>{_e(rec.get('rationale', ''))}</div>"
                "</li>"
            )
        sections.append(
            f"<section><h2>Recommendations</h2><ol class='numbered-list'>{''.join(items)}</ol></section>"
        )

    limitations = result.get("limitations") or []
    if limitations:
        items = "".join(f"<li>{_e(note)}</li>" for note in limitations)
        sections.append(
            f'<section><h2>Limitations</h2><ul class="bullet-list">{items}</ul></section>'
        )

    body_sections = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Compliance Report — {product}</title>
  <style>
    :root {{
      --bg: #f4f7fb;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --border: #e5e7eb;
      --primary: #0f4c81;
      --primary-soft: #e8f1fa;
      --success: #166534;
      --warning: #b45309;
      --danger: #b91c1c;
      --info: #1d4ed8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .report-header {{
      background: linear-gradient(135deg, #0f4c81 0%, #1d6fb8 100%);
      color: #fff;
      border-radius: 16px;
      padding: 32px;
      margin-bottom: 24px;
      box-shadow: 0 10px 30px rgba(15, 76, 129, 0.18);
    }}
    .report-header h1 {{
      margin: 0 0 8px;
      font-size: 2rem;
    }}
    .report-header .meta {{
      opacity: 0.92;
      font-size: 0.95rem;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .metric-card, section {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }}
    .metric-card {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .metric-value {{
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--primary);
    }}
    .metric-value.muted {{ color: var(--muted); font-size: 1.1rem; }}
    .metric-note {{ color: var(--muted); font-size: 0.85rem; }}
    section {{ margin-bottom: 24px; }}
    section h2 {{
      margin: 0 0 16px;
      font-size: 1.25rem;
      color: var(--primary);
      border-bottom: 2px solid var(--primary-soft);
      padding-bottom: 8px;
    }}
    .summary-box {{
      background: var(--primary-soft);
      border-left: 4px solid var(--primary);
      padding: 16px 18px;
      border-radius: 10px;
      margin-bottom: 24px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 10px 12px;
      vertical-align: top;
      text-align: left;
    }}
    th {{
      background: #f8fafc;
      font-weight: 600;
    }}
    .excerpt {{ color: var(--muted); font-size: 0.88rem; }}
    .badge, .tag {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .tag {{ background: #eef2ff; color: #3730a3; }}
    .status-aligned {{ background: #dcfce7; color: var(--success); }}
    .status-partial {{ background: #fef3c7; color: var(--warning); }}
    .status-missing, .status-verify, .status-neutral {{ background: #e5e7eb; color: #374151; }}
    .status-conflict {{ background: #fee2e2; color: var(--danger); }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
    .gap-card, .conflict-card {{
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      background: #fcfcfd;
    }}
    .gap-header {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .severity-high {{ border-color: #fecaca; }}
    .severity-medium {{ border-color: #fde68a; }}
    .severity-low {{ border-color: #d1fae5; }}
    .gap-type, .gap-id {{ color: var(--muted); font-size: 0.85rem; }}
    .action {{ margin-top: 10px; }}
    blockquote {{
      margin: 10px 0;
      padding: 10px 12px;
      background: #f8fafc;
      border-left: 3px solid var(--border);
    }}
    .bullet-list, .numbered-list {{ margin: 0; padding-left: 20px; }}
    .subtext {{ color: var(--muted); margin-top: 4px; }}
    .footer {{
      text-align: center;
      color: var(--muted);
      font-size: 0.85rem;
      margin-top: 24px;
    }}
    @media print {{
      body {{ background: #fff; }}
      .container {{ max-width: none; padding: 0; }}
      .report-header, section, .metric-card {{ box-shadow: none; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="report-header">
      <h1>Compliance Report: {product}</h1>
      <div class="meta">
        Report ID: { _e(report_id) } · Workflow ID: {workflow_id}<br />
        Generated: {generated}
      </div>
    </header>

    <div class="metrics">
      {score_block}
      <div class="metric-card">
        <span class="metric-label">Compliance Level</span>
        <span class="metric-value"><span class="badge {_status_class(result.get('compliance_level', 'undetermined'))}">{level}</span></span>
      </div>
      <div class="metric-card">
        <span class="metric-label">Assessment Confidence</span>
        <span class="metric-value">{confidence}</span>
      </div>
    </div>

    <div class="summary-box">
      <strong>Executive Summary</strong>
      <p>{summary}</p>
    </div>

    {body_sections}

    <div class="footer">
      Generated by PDF Compare Compliance Engine
    </div>
  </div>
</body>
</html>"""

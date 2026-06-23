COMPARISON_OUTPUT_SCHEMA = {
    "executive_summary": "2-4 sentences stating what can and cannot be concluded from available evidence",
    "assessment_confidence": "high | medium | low",
    "compliance_level": "compliant | partial | non_compliant | undetermined",
    "overall_compliance_score": None,
    "missing_evidence": [
        "Specific topics where detailed government rule text was not in the provided sources"
    ],
    "gov_requirements": [
        {
            "requirement_id": "GR-001",
            "source_url": "https://...",
            "source_title": "Section or notice title from source",
            "source_excerpt": "Exact short quote from government text",
            "requirement_text": "Stated obligation or referenced control area — do not invent details",
            "evidence_depth": "detailed_obligation | regulatory_reference | metadata_only",
            "category": "labeling | disposal | emissions | safety | documentation | substance_info | other",
        }
    ],
    "company_positions": [
        {
            "position_id": "CP-001",
            "source_excerpt": "Exact quote from company document",
            "topic": "...",
        }
    ],
    "alignments": [
        {
            "gov_requirement_id": "GR-001",
            "company_position_id": "CP-001 or null",
            "status": "aligned | partial | missing | cannot_verify | conflicting",
            "evidence": "Why this mapping was made, citing excerpts only",
            "gap_description": None,
            "recommended_action": None,
        }
    ],
    "coverage_gaps": [
        {
            "gov_requirement_id": "GR-002",
            "gap_type": "documentation_gap | cannot_verify | confirmed_missing",
            "severity": "high | medium | low",
            "description": "Evidence-based description — no invented government rules",
            "recommended_action": "Obtain full notice text / add company section / etc.",
        }
    ],
    "conflicts": [
        {
            "gov_requirement_id": "GR-003",
            "company_position_id": "CP-002",
            "government_excerpt": "Exact quote from government source",
            "company_excerpt": "Exact quote from company source",
            "description": "Explicit contradiction only",
            "recommended_action": "Update internal SOP",
        }
    ],
    "recommendations": [
        {
            "priority": 1,
            "action": "Obtain full text of Labelling Notice 2017 for detailed comparison",
            "rationale": "...",
            "affected_sections": [],
        }
    ],
    "limitations": ["Data quality and coverage limitations"],
}

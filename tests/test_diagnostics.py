"""Diagnostic and translation-report tests."""

from __future__ import annotations

from nodebridge.core.diagnostics import (
    Diagnostic,
    DiagnosticSeverity,
    OperationOutcome,
    TranslationReport,
    TranslationStatus,
)


def test_report_counts_and_text() -> None:
    report = TranslationReport(
        source_application="Blender",
        source_system="Geometry Nodes",
        target="Houdini SOP",
    )
    report.add_outcome(
        OperationOutcome("n1", "geometry.transform", TranslationStatus.EXACT)
    )
    report.add_outcome(
        OperationOutcome(
            "n2",
            "geometry.modify_position",
            TranslationStatus.EQUIVALENT,
            source_type="GeometryNodeSetPosition",
        )
    )
    report.add_outcome(
        OperationOutcome(
            "n3",
            "procedural.noise",
            TranslationStatus.APPROXIMATED,
            note="Mapped to Unified Noise",
            source_type="ShaderNodeTexNoise",
        )
    )
    report.add_outcome(
        OperationOutcome(
            "n4",
            "geometry.foobar",
            TranslationStatus.UNSUPPORTED,
            source_type="GeometryNodeFooBar",
        )
    )
    report.add_diagnostic(
        Diagnostic(
            code="NB-W100",
            message="Source graph relies on Blender-specific field behavior.",
            severity=DiagnosticSeverity.WARNING,
        )
    )
    counts = report.counts()
    assert counts[TranslationStatus.EXACT] == 1
    assert counts[TranslationStatus.UNSUPPORTED] == 1
    text = report.format_text()
    assert "Nodes analysed: 4" in text
    assert "GeometryNodeFooBar" in text
    assert "Unified Noise" in text
    assert "Blender-specific field behavior" in text
    payload = report.as_dict()
    assert payload["counts"]["exact"] == 1
    assert payload["diagnostics"][0]["code"] == "NB-W100"

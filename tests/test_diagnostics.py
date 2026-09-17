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
        target="Houdini",
        target_system="SOP",
    )
    report.add_outcome(
        OperationOutcome("n1", "geometry.transform", TranslationStatus.EXACT)
    )
    report.add_outcome(
        OperationOutcome(
            "n2",
            "geometry.instance",
            TranslationStatus.LOWERED,
            source_type="GeometryNodeInstanceOnPoints",
        )
    )
    report.add_outcome(
        OperationOutcome(
            "n3",
            "procedural.noise",
            TranslationStatus.APPROXIMATE,
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
    report.add_outcome(
        OperationOutcome(
            "n5",
            "math.add",
            TranslationStatus.CUSTOM_CODE,
            note="Attribute Wrangle",
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
    assert counts[TranslationStatus.CUSTOM_CODE] == 1
    text = report.format_text()
    assert "5 total" in text
    assert "EXACT" in text
    assert "GeometryNodeFooBar" in text
    assert "Unified Noise" in text
    assert "Blender-specific field behavior" in text
    payload = report.as_dict()
    assert payload["counts"]["exact"] == 1
    assert "compatibility_percent" not in payload
    assert payload["diagnostics"][0]["code"] == "NB-W100"
    assert TranslationStatus.EQUIVALENT is TranslationStatus.LOWERED
    assert TranslationStatus.APPROXIMATED is TranslationStatus.APPROXIMATE

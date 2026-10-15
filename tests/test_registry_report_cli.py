"""Translator registry, capability matrix, reports (golden files) and CLI."""

import json

import pytest
from helpers import EXAMPLES, compile_example, load_example

from nodebridge.backend.registry import get_backend, list_backends
from nodebridge.cli import main
from nodebridge.compiler.capabilities import capability, capability_matrix, format_matrix_markdown
from nodebridge.compiler.pipeline import CompileOptions, analyze
from nodebridge.ir.graph import TreeKind
from nodebridge.ir.operations import Category, OperationSpec, Port, get_operation, register_operation
from nodebridge.ir.types import DataType
from nodebridge.translation.confidence import Confidence, Strictness
from nodebridge.translation.fallback import FallbackSuggestion
from nodebridge.translation.registry import Translator, TranslatorRegistry, translator


def test_registry_rejects_duplicates_and_is_queryable():
    registry = TranslatorRegistry()
    translator("SCATTER", target="test", context="x", confidence=Confidence.EXACT, registry=registry)(lambda b, op: None)
    with pytest.raises(ValueError):
        translator("SCATTER", target="test", context="x", confidence=Confidence.EXACT, registry=registry)(lambda b, op: None)
    assert registry.kinds("test", "x") == {"SCATTER"}
    assert isinstance(registry.get("test", "x", "SCATTER"), Translator)


def test_backends_are_registered_with_contexts():
    assert [b.id for b in list_backends()] == ["houdini", "unreal"]
    assert get_backend("houdini").context_for(TreeKind.GEOMETRY) == "sop"
    assert get_backend("unreal").context_for(TreeKind.SHADER) == "material"
    with pytest.raises(KeyError):
        get_backend("maya")


def test_capability_matrix_is_derived_from_translators():
    assert capability("SCATTER", "houdini", "sop").confidence == Confidence.EQUIVALENT
    assert capability("SCATTER", "unreal", "pcg").implementation == "PCGSurfaceSamplerSettings"
    assert capability("EXTRUDE", "unreal", "pcg").confidence == Confidence.UNSUPPORTED
    rows = {row.kind: row for row in capability_matrix()}
    assert rows["TRANSFORM"].targets["houdini"][0][1].confidence == Confidence.EXACT
    assert "| `SCATTER` |" in format_matrix_markdown()


def test_new_operations_can_be_registered_without_compiler_changes():
    spec = OperationSpec("TEST_TWIST", Category.GEOMETRY, "test", (Port("geometry", DataType.GEOMETRY),), (Port("geometry", DataType.GEOMETRY),))
    register_operation(spec, replace=True)
    assert get_operation("TEST_TWIST") is spec
    assert capability("TEST_TWIST", "houdini", "sop").confidence == Confidence.UNSUPPORTED


@pytest.mark.parametrize("name", ["scatter", "building", "shader", "compositor"])
@pytest.mark.parametrize("target", ["houdini", "unreal"])
def test_expected_reports_and_scripts_match(name, target):
    """Golden files in examples/; regenerate with tools/regenerate_examples.py and review the diff."""
    result = compile_example(name, target)
    assert result.report.to_text() == (EXAMPLES / name / f"expected_report_{target}.txt").read_text(encoding="utf-8")
    assert result.code.code == (EXAMPLES / name / f"generated_{target}.py").read_text(encoding="utf-8")


def test_report_counts_add_up_and_explain_gaps():
    result = compile_example("scatter", "houdini")
    report = result.report
    assert sum(report.counts.values()) == report.operation_count
    text = report.to_text()
    assert "Approximations:" in text and "Coverage Noise" in text
    for entry in report.entries:
        assert entry.classification.explanation, entry.kind
    data = report.as_dict()
    assert data["counts"] == report.counts and data["source"]["application"].startswith("Blender")
    assert "semantically equivalent" in text


def test_strictness_blocks_without_dropping():
    result = analyze(load_example("scatter"), "houdini", CompileOptions(strictness=Strictness.ALLOW_EQUIVALENT))
    blocked = result.report.blocked
    assert blocked and all(e.classification.confidence == Confidence.APPROXIMATE for e in blocked)
    assert result.report.operation_count == compile_example("scatter", "houdini").report.operation_count


def test_fallback_provider_only_adds_suggestions():
    class Suggester:
        name = "test"

        def suggest(self, op, graph, target):
            return FallbackSuggestion(f"try a custom node for {op.kind}", provider=self.name)

    result = analyze(load_example("building"), "unreal", fallback=Suggester())
    suggestions = [e for e in result.report.entries if e.suggestion]
    assert suggestions and all(e.classification.confidence == Confidence.UNSUPPORTED for e in suggestions)


def test_cli_analyze_generate_and_capabilities(tmp_path, capsys):
    fixture = str(EXAMPLES / "scatter" / "scatter.graph.json")
    assert main(["analyze", fixture, "--target", "houdini"]) == 0
    assert "NodeBridge Translation Report" in capsys.readouterr().out
    assert main(["analyze", fixture, "--target", "unreal", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["target"]["id"] == "unreal"
    output = tmp_path / "scatter.py"
    assert main(["generate", fixture, "--target", "houdini", "-o", str(output)]) == 0
    assert output.read_text().startswith('"""NodeBridge')
    assert main(["capabilities", "--markdown"]) == 0
    assert "| Operation |" in capsys.readouterr().out

"""NodeBridge semantic compiler.

Host-independent analysis, normalization, planning, and lowering.
"""

from nodebridge.compiler.analysis import analyze_target_capabilities, can_implement
from nodebridge.compiler.normalization import normalize_graph
from nodebridge.compiler.pipeline import CompilationResult, compile_graph, compile_native
from nodebridge.compiler.planning import TranslationPlan, plan_translation

__all__ = [
    "CompilationResult",
    "TranslationPlan",
    "analyze_target_capabilities",
    "can_implement",
    "compile_graph",
    "compile_native",
    "normalize_graph",
    "plan_translation",
]

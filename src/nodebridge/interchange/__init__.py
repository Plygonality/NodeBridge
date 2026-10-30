"""Optional OpenUSD scene interchange.

USD is a portable evaluated scene plus a provenance manifest. It does not
replace Graph IR or Semantic IR, and it is not a native procedural backend.
Importing this package does not import ``pxr`` or ``bpy``.
"""

from .bundle import PackageInputs, publish_package
from .compare import CompareResult, StageSummary, Verdict, compare_summaries
from .errors import BundleError, PathSecurityError
from .manifest import BUNDLE_FORMAT, BUNDLE_FORMAT_VERSION, BundleManifest
from .provenance import content_hash, generator_id, group_id, operation_id
from .validate import ValidationReport, validate_bundle

__all__ = [
    "BUNDLE_FORMAT",
    "BUNDLE_FORMAT_VERSION",
    "BundleError",
    "BundleManifest",
    "CompareResult",
    "PackageInputs",
    "PathSecurityError",
    "StageSummary",
    "ValidationReport",
    "Verdict",
    "compare_summaries",
    "content_hash",
    "generator_id",
    "group_id",
    "operation_id",
    "publish_package",
    "validate_bundle",
]

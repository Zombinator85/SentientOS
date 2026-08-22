# Local runtime artifact acquisition

The shared exact-byte transport and custody mechanics are also used by the separate [dependency bundle acquisition](local_runtime_dependency_acquisition.md), without broadening this runtime artifact flow's GitHub trust policy.

Runtime acquisition is the first bounded production mutation after the metadata-only provisioning planner. It accepts a `selected` plan, validates the canonical production catalog again, binds every acquisition-relevant field, and requires an immutable `sentientos.local_runtime_acquisition_authorization:v1` confirmation of the exact plan digest, catalog digest, runtime, artifact hash and size, and absolute escrow root. The CLI is inspection-only by default; execution requires both `--execute` and `--confirm-plan-digest <exact digest>`.

The custody layout is `<escrow-root>/sha256/<64-hex-sha256>/<exact-wheel-filename>` plus `acquisition-receipt.json`. The executor rejects symlinked or non-directory path components, traversal filenames, unexpected existing content, and corrupt receipts. It streams bounded chunks through SHA-256 and an exact byte counter in a private staging directory, fsyncs the verified artifact and canonical receipt, and publishes the complete directory with a non-overwriting atomic rename. A concurrent winner is accepted only after complete verification. A verified existing address returns `already_present_verified` without transport; an incomplete or corrupt address is never repaired or overwritten.

Only the exact catalog HTTPS URL is requested. Credentials, floating/latest and package-index URLs are rejected. Redirects are bounded, must remain HTTPS, and may target only `github.com`, `objects.githubusercontent.com`, or `release-assets.githubusercontent.com`. Durable evidence records the canonical URL and sanitized hostnames, never signed redirect query strings. `Content-Length`, when present, must be exact; otherwise streaming stops immediately above the expected size and EOF must still be exact. Available space on the actual filesystem is checked before transport.

The deterministic semantic receipt digest uses canonical sorted-key JSON and excludes only optional operational `retrieved_at` metadata and the digest field itself. The receipt binds expected and observed size/hash, plan and catalog digests, authorization identity, content address, sanitized network route, and explicit negative authority facts.

## Deliberate boundary and dependency handoff

Artifact acquired **does not mean** package installed. Package installed **does not mean** runtime import verified. Runtime import verified **does not mean** model commissioned. Acquisition never invokes a package manager, creates an environment, extracts a wheel, writes site-packages, resolves dependencies, imports the runtime, loads a model, or commissions it. `runtime_dependency_custody_ready = false`.

The separate [offline dependency custody](local_runtime_dependencies.md) catalog now maps the runtime's requirements and Jinja2's transitive MarkupSafe requirement to exact wheels. Acquisition does not consume that dependency plan yet; a later bounded executor must acquire every selected wheel into verified local escrow before installation can become eligible.

The intended chain is: hardware observation → model artifact and execution-route selection → runtime provisioning plan → exact runtime artifact acquisition → dependency custody → bounded offline installation → runtime availability verification → model artifact acquisition/hash verification → launch configuration → commissioning → first boot.

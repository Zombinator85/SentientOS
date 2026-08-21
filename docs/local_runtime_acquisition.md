# Local runtime artifact acquisition

Runtime acquisition is the first bounded production mutation after the metadata-only provisioning planner. It accepts a `selected` plan, validates the canonical production catalog again, binds every acquisition-relevant field, and requires an immutable `sentientos.local_runtime_acquisition_authorization:v1` confirmation of the exact plan digest, catalog digest, runtime, artifact hash and size, and absolute escrow root. The CLI is inspection-only by default; execution requires both `--execute` and `--confirm-plan-digest <exact digest>`.

The custody layout is `<escrow-root>/sha256/<64-hex-sha256>/<exact-wheel-filename>` plus `acquisition-receipt.json`. The executor rejects symlinked or non-directory path components, traversal filenames, unexpected existing content, and corrupt receipts. It streams bounded chunks through SHA-256 and an exact byte counter in a private staging directory, fsyncs the verified artifact and canonical receipt, and publishes the complete directory with a non-overwriting atomic rename. A concurrent winner is accepted only after complete verification. A verified existing address returns `already_present_verified` without transport; an incomplete or corrupt address is never repaired or overwritten.

Only the exact catalog HTTPS URL is requested. Credentials, floating/latest and package-index URLs are rejected. Redirects are bounded, must remain HTTPS, and may target only `github.com`, `objects.githubusercontent.com`, or `release-assets.githubusercontent.com`. Durable evidence records the canonical URL and sanitized hostnames, never signed redirect query strings. `Content-Length`, when present, must be exact; otherwise streaming stops immediately above the expected size and EOF must still be exact. Available space on the actual filesystem is checked before transport.

The deterministic semantic receipt digest uses canonical sorted-key JSON and excludes only optional operational `retrieved_at` metadata and the digest field itself. The receipt binds expected and observed size/hash, plan and catalog digests, authorization identity, content address, sanitized network route, and explicit negative authority facts.

## Deliberate boundary and dependency gap

Artifact acquired **does not mean** package installed. Package installed **does not mean** runtime import verified. Runtime import verified **does not mean** model commissioned. Acquisition never invokes a package manager, creates an environment, extracts a wheel, writes site-packages, resolves dependencies, imports the runtime, loads a model, or commissions it. `runtime_dependency_custody_ready = false`.

Upstream `llama-cpp-python` 0.3.35 declares unresolved direct requirements `typing-extensions >= 4.5.0`, `numpy >= 1.20.0`, `diskcache >= 5.6.1`, and `jinja2 >= 2.11.3`. Jinja2's transitive MarkupSafe requirement is a dependency-closure concern for the next custody task; these broad expressions are not exact-byte custody.

The intended chain is: hardware observation → model artifact and execution-route selection → runtime provisioning plan → exact runtime artifact acquisition → dependency custody → bounded offline installation → runtime availability verification → model artifact acquisition/hash verification → launch configuration → commissioning → first boot.

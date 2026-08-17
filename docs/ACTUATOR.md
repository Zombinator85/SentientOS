# Actuator process execution

## Built-ins and the external-code boundary

The actuator runtime provides the canonical built-in types `shell`, `http`, `file`,
`email`, `webhook`, `workflow`, and `talkback`. Initialization registers only these
built-ins and is idempotent. The temporary `load_external_plugins` keyword remains
for compatibility, but requesting it fails deterministically with `external actuator
plugins are disabled` before registering or inspecting anything.

Legacy filesystem-loaded external actuator Python execution has been removed.
`ACT_PLUGINS_DIR` no longer grants actuator code-loading authority: the actuator
subsystem does not scan, read, import, compile, or execute arbitrary `.py` files from
that directory. Its former `plugins` CLI command and reload option have also been
removed, so actuator administration cannot turn directory contents into executable
code or remove built-in registrations.

The repository's `plugin_framework` is a separate plugin system and is not implicitly
bridged into actuators. This boundary does not claim that all repository plugin
systems are isolated. Any future external actuator extensibility requires a separately
designed and authorized identity, authority, and isolation contract; directory
presence and filename extensions alone confer no authority.

The canonical shell-actuator intent is structured data:

```json
{"type": "shell", "argv": ["program", "arg1", "arg2"]}
```

The actuator validates and copies `argv`, admits it through structured command policy,
and passes the resulting immutable sequence once to `subprocess.run` with
`shell=False`. It never joins arguments into executable text. Consequently `;`, `|`,
`&&`, `>`, `$HOME`, and `*.txt` inside an explicit argument are ordinary data. The
actuator performs no globbing, environment expansion, redirection, substitution,
chaining, or background execution.

## Validation and compatibility

`argv` must be a nonempty list or tuple of strings, with a nonempty `argv[0]` and no
NUL. The limits are 128 arguments, 4,096 UTF-8 bytes per argument, and 32,768 UTF-8
bytes in total. Invalid or over-budget input fails closed before authorization.

Legacy `cmd` remains temporarily available for simple command-and-argument callers.
It is parsed once by the local, non-executing `shlex` tokenizer and only the resulting
argv is executed. Semicolons, pipes, `&&`, `||`, redirects, command/process
substitution, backticks, background markers, and command-separating newlines are
rejected. Ambiguous input must migrate to explicit `argv`; the original text is kept
only as `legacy_cmd` audit data.

## Command authorization and executable custody

The shipped `shell` policy is empty and therefore grants no process authority. An
operator-provided rule has exactly three fields: a case-sensitive logical `alias`, an
absolute `executable` path, and an `arguments` list describing every argument slot.
Legacy string entries, additional rule fields, bare executable names, glob patterns,
and regular expressions are malformed policy and fail closed. A caller may identify a
rule by its exact alias or its configured canonical executable path. The alias is a
lookup key only and is never passed to the operating system.

```yaml
shell:
  - alias: inspect-release
    executable: /operator/admitted/path/to/tool
    arguments:
      - {type: literal, value: "inspect"}
      - {type: one_of, values: ["brief", "full"]}
```

Executable configuration rejects NUL, non-absolute and nonexistent paths, directories,
and, on POSIX, regular files without executable permission. Configured symlinks are
resolved; their canonical target is the logical policy identity installed as `argv[0]`.
After exact rule and argument admission, Linux opens that target with a descriptor-relative,
component-by-component no-follow walk. The descriptor-bound source must be a regular,
executable file no larger than 128 MiB.

Before privilege approval, bounded descriptor I/O copies those bytes into an anonymous
`memfd` and derives an internal SHA-256 evidence digest. The copy is rejected if source
device, inode, size, modification time, status-change time, or copied length changed
across pre-copy and post-copy `fstat()` observations. Only native ELF is accepted.
Shebang scripts fail closed: a future interpreter workflow would need separately admitted
and immutably bound interpreter code and input custody.

The snapshot is sealed against writes, growth, shrinkage, and seal changes. Its writable
construction descriptor is closed; only a reopened read-only descriptor crosses process
creation. `subprocess.run` retains canonical policy identity as `argv[0]`, while its
actuator-constructed `executable` is `/proc/self/fd/<snapshot-fd>`. The exact internal
`pass_fds` tuple contains that descriptor and the held command-cwd descriptor described
below. Callers cannot provide either field or descriptors. Replacement,
unlink, rename, permission changes, symlink retargeting, and in-place source modification
after snapshot completion cannot substitute current-invocation code. No PATH search or
post-approval policy-path reopen occurs.

This requires Linux `memfd_create` sealing and `/proc/self/fd`; unsupported platforms
fail closed rather than returning to pathname execution. The snapshot binds the main ELF
image, not its dynamic ELF interpreter or shared libraries, which remain separate runtime
dependencies. Generic interpreters, network clients such as curl/wget/ping, package
managers, and service managers receive no implicit authority.

Argument policy is complete and exact: supplied arity must equal configured arity.
`literal` admits one exact string; `one_of` admits one member of an explicit finite
list. These are the only supported slot types. Unknown types are malformed policy.
Path-looking `literal` and `one_of` values remain exact strings: they are not resolved,
opened, translated, or rejected merely because they contain separators. There is no
arbitrary-string, regex, glob, script, interpreter, or generic path shortcut.
For example, configuring Python does not authorize `-c` code or a `.py` path unless
each exact argument is explicitly represented by the rule.

The final order is: validate caller argv; parse and canonicalize the matching command
rule and every argument; bind and seal its executable snapshot; lexically validate the
cwd and bind its existing directory object; invoke `_authorize_effect()` immediately
before the single `subprocess.run` boundary; then execute the already-bound snapshot
with `shell=False`.
Denied command policy, executable objects, arguments, or paths construct no process.
Legacy `cmd` differs only in parsing and passes through this identical sequence.

## Child process-state custody

Authorization of an executable and its complete argument vector does not authorize
the actuator host's ambient process environment. The protected child receives a
fresh, deliberately empty environment. In particular, `PATH`, parent secrets and
tokens, proxy variables, and dynamic-loader or language-interpreter injection values
are absent by construction; the implementation does not copy and then filter the
parent environment. Standard input is explicitly `DEVNULL`, while stdout and stderr
remain captured. `close_fds=True` closes unrelated inherited descriptors. The only
exceptions are exactly two internally created custody descriptors: the read-only sealed
executable snapshot and the opened cwd directory. Neither is caller input or a generic
descriptor-passing API.

There is no command-environment policy and callers cannot supply environment or
generic process-control options. Unknown shell-intent fields fail closed. A future
executable that demonstrably needs environment state requires a separate,
executable-specific authority design. Until that exists, an executable that cannot
operate with an empty environment is unsuitable for actuator admission; ambient
inheritance is not a compatibility fallback.

This custody is process-state isolation, not an operating-system sandbox. OS
credentials and user identity are unchanged. Filesystem visibility and the network
capability of an explicitly admitted executable are unchanged. A child may itself
interpret or open data or code named by an authorized argument.
Dynamic ELF interpreter and shared-library content is not pinned. OS identity,
filesystem visibility, and network privileges remain unchanged. These residual
boundaries are not executable-snapshot authority.

## Filesystem sandbox boundary

File writes use descriptor-relative, no-follow custody. The configured sandbox root
is created and opened one component at a time from an opened filesystem-root or
current-directory descriptor. Each caller-controlled parent is opened relative to
the already-bound parent descriptor; a missing parent is created with `mkdir(dir_fd=)`
and then opened the same way. Existing symlinks are never traversed, whether they
point inward or outward. This is intentionally stricter than the shell path policy.

Caller-supplied absolute paths are rejected, including absolute paths that point back
inside the sandbox. For file writes, `.` components normalize away and every `..`
component is rejected as an authority reduction; ordinary relative nesting remains
accepted. File intents require a nonempty path. Non-string and NUL-containing path
values fail closed.

The final leaf is opened with `O_NOFOLLOW` relative to the bound parent. `fstat`
requires a regular file and rejects a multiple-link inode before truncation, closing
the practical external hardlink-alias case. Descriptor I/O truncates and writes that
opened object; no caller pathname is re-resolved after custody. A final file need not
exist, so safe missing parents and leaves can still be created. The actuator does not
apply shell, environment-variable, or tilde expansion to paths; those characters are
literal path data. The returned `{"written": ...}` pathname is reporting metadata,
not write authority, and may no longer name the descriptor-bound object if another
party renames it concurrently.

Command cwd uses a separate existing-only descriptor walk. It is a lexical relative
selection below the configured sandbox root: empty and `.` components normalize away,
every `..` component and every absolute, non-string, or NUL-containing value is rejected,
and `.` selects the root. The root and every selected directory must already exist;
command admission creates nothing. Components are opened with `dir_fd`, `O_DIRECTORY`,
and `O_NOFOLLOW`, so inward and outward symlinks are both rejected. Tilde, environment,
and glob expansion do not occur.

The final cwd descriptor is held before privilege approval. The child receives
`cwd=/proc/self/fd/<held-directory-fd>` and that exact fd in the narrow internal
descriptor tuple, so rename, symlink substitution, real-directory replacement, or even
replacement of the configured root namespace entry after admission cannot redirect the
current invocation. This proc path is actuator-owned object access, not caller path
authority. No cwd pathname is reopened after approval, the parent never calls `chdir`,
and any reported pathname is selection metadata rather than immutable namespace identity.

Platforms without POSIX `dir_fd`, `O_DIRECTORY`, `O_NOFOLLOW`, and Linux
`/proc/self/fd` support fail closed; there is no pathname fallback. Windows therefore
requires a future handle-native implementation. File write and command cwd have
descriptor/object custody. The former `sandbox_path`
slot canonicalized a caller-relative path beneath the sandbox and handed the resulting
pathname string to an arbitrary external executable. That contract is retired. It did
not specify whether the argument meant an existing regular file, an existing directory,
an object to read, an object to mutate, a destination to create, a tree root, or merely
path-shaped literal data. One generic path type cannot bind all of those semantics safely.

A future command needing filesystem arguments must declare object-specific authority.
Illustrative possibilities include an existing read-only file object, an existing
directory object, a create-only destination beneath a held directory, a
replace-existing-file object, or a fixed literal pathname whose identity is intentionally
part of the executable's trusted contract. These are directions, not slot types
standardized or implemented here.

The custody distinction is operational: the actuator consumes `cwd`, so it can retain
the selected directory descriptor; the actuator performs `file_write`, so it can retain
the mutation object's descriptor. An arbitrary child consumes a generic command
argument, and replacing a pathname with an fd-backed proc path cannot be assumed to
preserve that child's semantics. Retirement therefore reduces authority instead of
adding a third descriptor. An admitted child can independently open any path allowed
by its OS identity;
dynamic ELF interpreter and shared-library dependencies remain unpinned; OS identity,
filesystem privileges, and network privileges are unchanged.

## Templates, async, dry-run, and records

Repository shell templates store an argv list. Each placeholder occupies one list
slot, so a parameter such as `hello; touch nope` remains one argument rather than
executable syntax. Placeholder discovery recursively examines dictionaries and lists.

Async submission normalizes and copies the intent before queueing; workers receive
structured argv and never command text. Dry-run normalizes and reports the canonical
`argv` while starting no process. Action logs and reflections likewise retain
structured argv. When legacy `cmd` was supplied, records distinguish `legacy_cmd`
from normalized and executed `argv`.

Templates express and expand intent only. Declaration and placeholder substitution do
not authorize a command or argument: expanded argv traverses the same structured rule
validator as a direct shell intent. Thus the shipped `systemctl restart {service}` and
`ls {path}` examples remain inactive with the empty policy; a future service rule must
use finite `one_of` values. There is currently no generic structured rule capable of
authorizing arbitrary `{path}` values. The `list_files` template remains only an
intent-expansion example; an active file-list operation requires an object-specific
filesystem authority contract.

This repair closes the prior shell-string authorization/execution mismatch: the argv
that is authorized is the argv that is executed.

## Outbound endpoint policy

HTTP fetches and webhooks share one structural URL policy. The `http` list in
`config/act_whitelist.yml` contains canonical origins, optionally followed by a path
scope. An origin-only entry such as `https://api.example.com` authorizes only that
scheme, hostname, and effective port, for every path on that origin. An entry such as
`https://hooks.example.com/events` authorizes exactly `/events` and descendants such
as `/events/new`; it does not authorize `/eventside`. Queries remain request data and
cannot change the parsed host. Policy entries containing a query or fragment are
invalid and ignored. Generic globs, regular expressions, `*`, and hostname wildcards
are not supported.

URLs are parsed with the standard-library URL parser before authorization. Only HTTP
and HTTPS are supported. Hostnames are lower-cased and IDNA-canonicalized, a trailing
DNS dot is normalized away, IPv4 and IPv6 literals use their canonical address form,
and default ports normalize to HTTP 80 and HTTPS 443. IPv6 is rendered with brackets.
Missing hosts, malformed ports, control characters, and embedded username/password
userinfo are rejected. Fragments are removed because they are not network request
data; the canonicalized URL that passed policy is the URL given to the client.

HTTP intents admit only `url`, `method`, `headers`, `body`, and `json` request data. Methods are canonicalized to GET, POST, PUT, PATCH, DELETE, HEAD, or OPTIONS. Raw bodies and deterministic JSON bodies are mutually exclusive and limited to 1 MiB. Header names and values reject controls, while Host, Connection, Proxy-Connection, Proxy-Authorization, Transfer-Encoding, Content-Length, Upgrade, TE, and Trailer are reserved to the transport. The canonical URL supplies Host, including a non-default port. Unknown fields fail closed rather than becoming client-library options.

After lexical policy and privilege approval, a DNS hostname is resolved exactly once with a maximum of 16 unique TCP candidates. The complete answer fails closed if any candidate is malformed or non-global, so ordinary hostname authority cannot silently acquire loopback, private, link-local, multicast, unspecified, or reserved authority. An exact configured IP literal deliberately remains usable, including a special literal, and performs no DNS lookup. Candidate failover uses only that snapshot. The standard-library transport connects directly to its exact sockaddr; HTTP(S) proxy environment variables and caller proxy options have no role.

HTTPS wraps the pinned socket with the system default verifying TLS context and uses the canonical logical hostname for SNI and certificate hostname verification. System CA trust and resolver authenticity/DNSSEC are not strengthened or claimed here. Exactly one HTTP transaction is performed: redirect Location remains response data and is never followed. Response bodies are limited to 1 MiB and decoded using the declared charset or UTF-8 with deterministic replacement. Webhook POST uses this same transport and custody chain with deterministic JSON. The shipped policy remains empty and fail closed; no wildcard or destination was added.

### Mail policy

The `smtp` list authorizes exact `hostname:port` pairs, for example
`smtp.example.com:587` (or `[::1]:2525` for IPv6). `SMTP_HOST` and `SMTP_PORT` propose
the connection endpoint but do not authorize it. Hostnames compare using canonical,
case-insensitive DNS spelling and ports must be in 1-65535. The endpoint and recipient
are both authorized before `smtplib.SMTP` is constructed, so denial opens no SMTP
connection.

The `email` list supports exact single mailboxes and an optional exact-domain form,
`*@example.com`. Domain scopes match only that canonical domain, never suffixes such
as `example.com.evil`; exact mailbox local parts remain case-sensitive. The bounded
mailbox grammar accepts one `@` and a conservative dot-atom-like local part rather
than attempting complete RFC parsing. Recipient, configured sender, and subject
control characters (including CR/LF header injection) are rejected before connection.
The single-recipient interface remains single-recipient.

SMTP transport behavior is otherwise unchanged: the actuator uses `smtplib.SMTP` and
optional authentication, but does not enable STARTTLS or implicit TLS. Endpoint
authorization does not imply transport confidentiality, and TLS modernization is a
separate task. Credentials are never included in policy errors or return values.

Example fail-closed configuration with explicit authority:

```yaml
http: ["https://api.example.com", "https://hooks.example.com/events"]
smtp: ["smtp.example.com:587"]
email: ["operator@example.com", "*@alerts.example.com"]
```

Notification subscriptions continue to store their webhook or email targets without
being rewritten or treated as policy. At send time they call the protected actuator,
where the current endpoint and recipient policy is authoritative; a formerly stored
but unauthorized target fails closed. Async work retains the copied target and is
authorized when executed. General actuator dry-run dispatch performs no HTTP,
webhook, or SMTP effect and records the unexecuted intent; normal logs preserve target
data and never add SMTP credentials.

This repair only narrows destinations reachable through existing outbound effects; it
grants no new networking authority. Plugin-framework isolation and repository-wide
mypy/tool compatibility remain separate follow-ups.

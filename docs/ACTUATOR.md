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
      - {type: sandbox_path}
```

Executable configuration rejects NUL, non-absolute and nonexistent paths, directories,
and, on POSIX, regular files without executable permission. Symlinks are deliberately
resolved and the canonical target path that passed policy is installed as `argv[0]`.
The actuator never calls `which` and never consults ambient `PATH` to select the
executable. Generic interpreters, network clients such as curl/wget/ping, package
managers, and service managers receive no implicit authority.

Argument policy is complete and exact: supplied arity must equal configured arity.
`literal` admits one exact string; `one_of` admits one member of an explicit finite
list; and `sandbox_path` admits a nonempty caller-relative path through the same
resolved sandbox-ancestry boundary described below, passing its canonical path to the
program. There is no arbitrary-string, regex, glob, script, or interpreter shortcut.
For example, configuring Python does not authorize `-c` code or a `.py` path unless
each exact argument is explicitly represented by the rule.

The final order is: validate caller argv; parse and canonicalize the matching command
rule and every argument; establish and validate the sandbox cwd; invoke
`_authorize_effect()` immediately before the single `subprocess.run` boundary; then
execute the authorized canonical argv with `shell=False`. Denied command policy,
arguments, or paths construct no process. Legacy `cmd` differs only in its parsing
step and passes through this identical sequence.

This establishes path identity at authorization time, not immutable binary-content
identity. Replacement of the executable after validation and before process creation
remains a binary-content/TOCTOU concern. The child also inherits the existing process
environment, whose broader custody is unchanged and separate. No descriptor-relative
filesystem TOCTOU claim is made.

## Filesystem sandbox boundary

File-write destinations and shell working directories share one containment rule.
For each decision, the sandbox root is resolved and that resolved root is the custody
boundary. The caller's relative path is then resolved, including existing parent
symlinks, and is admitted only when `Path.relative_to()` proves that the result is the
root itself or a descendant by native path components. Textual prefix similarity has
no authority: a sibling such as `sbox_evil` is outside `sbox`.

Caller-supplied absolute paths are rejected, including absolute paths that point back
inside the sandbox. `.` and the shell cwd default select the sandbox root; ordinary
relative nesting and `./child` are accepted, while `..` normalization is accepted
only when its resolved result remains within the boundary. File intents require a
nonempty path. Non-string and NUL-containing path values fail closed.

An existing symlink is governed by its resolved destination. A symlink that resolves
outside the sandbox is rejected before a write or process launch; one whose resolved
destination remains inside is allowed. A final file need not exist, so safe missing
parents and leaves can still be created after validation. The actuator does not apply
shell, environment-variable, or tilde expansion to paths; those characters are
literal path data. Native `pathlib` component, drive, and case semantics apply, and
ambiguous cross-drive or otherwise non-relative results fail closed.

This resolved-path check closes textual-prefix and already-present symlink escapes,
but it is not descriptor-relative custody. A party able to mutate directories or
symlinks between validation and the later mkdir, write, or process operation may
still create a check-to-effect race. Descriptor-relative/no-follow hardening remains
a separate filesystem-custody problem. This repair does not change or claim to close
independent URL/SMTP or plugin-isolation concerns.

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
use finite `one_of` values, and a path placeholder must use `sandbox_path` rather than
granting arbitrary host-path access.

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

Both the Requests and urllib backends disable automatic redirects. A redirect
response is therefore never authority to contact its target, and no second request is
made. Requests receives `allow_redirects=False`; urllib uses a no-redirect handler.
Webhook POSTs use exactly the same canonical validator and redirect posture as HTTP
fetches.

The shipped `http` list is empty and therefore fails closed. Local, private,
loopback, link-local, multicast, unspecified, and other special IP literals receive
no implicit authority: an exact canonical literal origin and port must be configured,
just like any other destination. This lexical endpoint policy does not resolve a DNS
hostname before authorization and does not claim to prevent DNS rebinding or a DNS
answer that maps an explicitly authorized hostname to a special address. Resolver
custody and rebinding defenses remain a separate follow-up.

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
grants no new networking authority. Plugin-framework isolation, inherited-environment custody, executable-content
replacement, descriptor-relative filesystem TOCTOU custody, and repository-wide mypy/tool
compatibility remain separate follow-ups.

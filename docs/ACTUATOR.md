# Actuator process execution

The canonical shell-actuator intent is structured data:

```json
{"type": "shell", "argv": ["program", "arg1", "arg2"]}
```

The actuator validates and copies `argv`, authorizes that same immutable sequence at
the protected effect boundary, and passes it once to `subprocess.run` with
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

## Authorization and resolution

Shell whitelist patterns match the complete, case-sensitive `argv[0]`. Plain entries
are exact; glob entries use full-name glob matching; anchored regular expressions use
full matching. An entry such as `python` therefore does not authorize `python-evil`.
Execution uses exactly that authorized `argv[0]`. A bare executable name is still
resolved by the operating system using the process `PATH`, so replacement or races in
that externally controlled search path remain a bounded risk; this change does not
claim binary identity, signing, or package custody.

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
grants no new networking authority. Plugin isolation, executable `PATH` identity,
descriptor-relative filesystem TOCTOU custody, and repository-wide mypy/tool
compatibility remain separate follow-ups.

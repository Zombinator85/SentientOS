"""Render an inert, operator-installed Windows maintenance wake bundle."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping
from xml.etree import ElementTree as ET

MANIFEST_SCHEMA = "sentientos.maintenance_windows_deployment_manifest:v1"
INDEX_SCHEMA = "sentientos.maintenance_windows_deployment_index:v1"
ARTIFACT_NAMES = ("maintenance-wake.ps1", "maintenance-wake-task.xml")
INDEX_NAME = "maintenance-wake-deployment-index.json"
FIELDS = {
    "schema_version", "repository_root", "expected_repository_sha", "python_executable",
    "wake_configuration_path", "external_log_directory", "deployment_output_directory",
    "task_name", "working_directory", "trigger_type", "trigger_interval_or_exact_schedule",
    "execution_timeout", "task_execution_account_mode", "allow_on_battery", "wake_from_sleep",
    "missed_runs_start_later", "maximum_concurrent_instances", "launcher_stdout_path",
    "launcher_stderr_path", "manifest_digest",
}
PATH_FIELDS = {
    "repository_root", "python_executable", "wake_configuration_path", "external_log_directory",
    "deployment_output_directory", "working_directory", "launcher_stdout_path", "launcher_stderr_path",
}
SECRET_WORDS = re.compile(r"(?i)(password|passwd|credential|secret|token|api[_-]?key)")
SHA = re.compile(r"^[0-9a-f]{40}$")
ISO_DURATION = re.compile(r"^PT(?:[1-9][0-9]*H)?(?:[1-9][0-9]*M)?(?:[1-9][0-9]*S)?$")
ISO_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"


def byte_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _manifest_digest(value: Mapping[str, Any]) -> str:
    return byte_digest(canonical_json_bytes({k: v for k, v in value.items() if k != "manifest_digest"}))


def _windows_absolute(value: Any) -> bool:
    if not isinstance(value, str) or not value or any(c in value for c in "\r\n\0"):
        return False
    path = PureWindowsPath(value)
    return path.is_absolute() and bool(path.drive) and not any(part in {".", ".."} for part in path.parts)


def _under(child: str, parent: str) -> bool:
    c = tuple(x.casefold() for x in PureWindowsPath(child).parts)
    p = tuple(x.casefold() for x in PureWindowsPath(parent).parts)
    return len(c) >= len(p) and c[:len(p)] == p


def validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) - FIELDS or not (FIELDS - {"manifest_digest"}).issubset(value):
        raise ValueError("invalid_closed_manifest")
    if value.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError("invalid_schema_version")
    result = dict(value)
    if SECRET_WORDS.search(" ".join(str(k) for k in result)):
        raise ValueError("credential_or_secret_field_forbidden")
    for field in PATH_FIELDS:
        if not _windows_absolute(result[field]):
            raise ValueError(field + "_must_be_absolute_windows_path")
    repo = str(result["repository_root"])
    for field in ("external_log_directory", "deployment_output_directory", "launcher_stdout_path", "launcher_stderr_path"):
        if _under(str(result[field]), repo):
            raise ValueError(field + "_must_be_external_to_repository")
    if not _under(str(result["launcher_stdout_path"]), str(result["external_log_directory"])) or not _under(str(result["launcher_stderr_path"]), str(result["external_log_directory"])):
        raise ValueError("launcher_logs_outside_external_log_directory")
    if not SHA.fullmatch(str(result["expected_repository_sha"])):
        raise ValueError("expected_repository_sha_invalid")
    if result["working_directory"].casefold() != repo.casefold():
        raise ValueError("working_directory_must_equal_repository_root")
    for field in ("allow_on_battery", "wake_from_sleep", "missed_runs_start_later"):
        if type(result[field]) is not bool:
            raise ValueError(field + "_must_be_boolean")
    if result["maximum_concurrent_instances"] != 1:
        raise ValueError("maximum_concurrent_instances_must_be_one")
    if result["task_execution_account_mode"] not in {"system", "interactive_users"}:
        raise ValueError("unsupported_task_execution_account_mode")
    trigger = result["trigger_type"]
    schedule = str(result["trigger_interval_or_exact_schedule"])
    if trigger == "interval":
        if not ISO_DURATION.fullmatch(schedule) or schedule == "PT":
            raise ValueError("unsupported_trigger_interval")
    elif trigger in {"once", "daily"}:
        if not ISO_TIME.fullmatch(schedule):
            raise ValueError("unsupported_exact_schedule")
    else:
        raise ValueError("unsupported_trigger_type")
    if not ISO_DURATION.fullmatch(str(result["execution_timeout"])) or result["execution_timeout"] == "PT":
        raise ValueError("unsupported_execution_timeout")
    for field in ("task_name",):
        if not isinstance(result[field], str) or not result[field].strip() or any(c in result[field] for c in "\r\n\0"):
            raise ValueError(field + "_invalid")
    encoded = canonical_json_bytes(result)
    if SECRET_WORDS.search(encoded.decode()):
        raise ValueError("embedded_secret_like_value_forbidden")
    expected = _manifest_digest(result)
    if result.get("manifest_digest") not in (None, "", expected):
        raise ValueError("manifest_digest_mismatch")
    result["manifest_digest"] = expected
    return result


def load_manifest(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("manifest_path_unsafe")
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("manifest_not_object")
    return validate_manifest(value)


def template() -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA,
        "repository_root": "C:\\SentientOS", "expected_repository_sha": "0" * 40,
        "python_executable": "C:\\Python312\\python.exe",
        "wake_configuration_path": "C:\\SentientOS-configuration\\maintenance-wake.json",
        "external_log_directory": "C:\\SentientOS-custody\\logs",
        "deployment_output_directory": "C:\\SentientOS-custody\\deployment",
        "task_name": "SentientOS Maintenance Wake", "working_directory": "C:\\SentientOS",
        "trigger_type": "interval", "trigger_interval_or_exact_schedule": "PT15M",
        "execution_timeout": "PT10M", "task_execution_account_mode": "system",
        "allow_on_battery": False, "wake_from_sleep": False, "missed_runs_start_later": False,
        "maximum_concurrent_instances": 1,
        "launcher_stdout_path": "C:\\SentientOS-custody\\logs\\maintenance-wake.stdout.log",
        "launcher_stderr_path": "C:\\SentientOS-custody\\logs\\maintenance-wake.stderr.log",
    }
    value["manifest_digest"] = _manifest_digest(value)
    return value


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_launcher(cfg: Mapping[str, Any]) -> bytes:
    script = PureWindowsPath(str(cfg["repository_root"])) / "scripts" / "maintenance_wake_cycle.py"
    lines = [
        "$ErrorActionPreference = 'Stop'", "Set-StrictMode -Version Latest",
        f"$expectedRepositorySha = {_ps_quote(str(cfg['expected_repository_sha']))}",
        "$evaluationTime = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ')",
        f"$repositoryRoot = {_ps_quote(str(cfg['repository_root']))}",
        f"$pythonExecutable = {_ps_quote(str(cfg['python_executable']))}",
        f"$wakeScript = {_ps_quote(str(script))}",
        f"$wakeConfiguration = {_ps_quote(str(cfg['wake_configuration_path']))}",
        f"$stdoutPath = {_ps_quote(str(cfg['launcher_stdout_path']))}",
        f"$stderrPath = {_ps_quote(str(cfg['launcher_stderr_path']))}",
        "Set-Location -LiteralPath $repositoryRoot",
        "$arguments = @($wakeScript, '--config', $wakeConfiguration, '--evaluation-time', $evaluationTime, 'wake-once')",
        "$process = Start-Process -FilePath $pythonExecutable -ArgumentList $arguments -WorkingDirectory $repositoryRoot -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -Wait -PassThru -NoNewWindow",
        "exit $process.ExitCode", "",
    ]
    return "\r\n".join(lines).encode("utf-8")


def _bool(value: bool) -> str:
    return "true" if value else "false"


def render_xml(cfg: Mapping[str, Any]) -> bytes:
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", ns)
    def tag(name: str) -> str:
        return f"{{{ns}}}{name}"
    root = ET.Element(tag("Task"), {"version": "1.4"})
    triggers = ET.SubElement(root, tag("Triggers"))
    trigger_type = str(cfg["trigger_type"])
    node = ET.SubElement(triggers, tag("TimeTrigger" if trigger_type in {"interval", "once"} else "CalendarTrigger"))
    ET.SubElement(node, tag("StartBoundary")).text = "2000-01-01T00:00:00Z" if trigger_type == "interval" else str(cfg["trigger_interval_or_exact_schedule"])
    ET.SubElement(node, tag("Enabled")).text = "true"
    if trigger_type == "interval":
        repeat = ET.SubElement(node, tag("Repetition")); ET.SubElement(repeat, tag("Interval")).text = str(cfg["trigger_interval_or_exact_schedule"]); ET.SubElement(repeat, tag("StopAtDurationEnd")).text = "false"
    elif trigger_type == "daily":
        byday = ET.SubElement(node, tag("ScheduleByDay")); ET.SubElement(byday, tag("DaysInterval")).text = "1"
    principals = ET.SubElement(root, tag("Principals")); principal = ET.SubElement(principals, tag("Principal"), {"id": "Author"})
    if cfg["task_execution_account_mode"] == "system":
        ET.SubElement(principal, tag("UserId")).text = "S-1-5-18"; ET.SubElement(principal, tag("LogonType")).text = "ServiceAccount"
    else:
        ET.SubElement(principal, tag("GroupId")).text = "S-1-5-4"; ET.SubElement(principal, tag("LogonType")).text = "Group"
    ET.SubElement(principal, tag("RunLevel")).text = "LeastPrivilege"
    settings = ET.SubElement(root, tag("Settings"))
    ET.SubElement(settings, tag("MultipleInstancesPolicy")).text = "IgnoreNew"
    ET.SubElement(settings, tag("DisallowStartIfOnBatteries")).text = _bool(not bool(cfg["allow_on_battery"]))
    ET.SubElement(settings, tag("StopIfGoingOnBatteries")).text = _bool(not bool(cfg["allow_on_battery"]))
    ET.SubElement(settings, tag("StartWhenAvailable")).text = _bool(bool(cfg["missed_runs_start_later"]))
    ET.SubElement(settings, tag("WakeToRun")).text = _bool(bool(cfg["wake_from_sleep"]))
    ET.SubElement(settings, tag("ExecutionTimeLimit")).text = str(cfg["execution_timeout"])
    actions = ET.SubElement(root, tag("Actions"), {"Context": "Author"}); execute = ET.SubElement(actions, tag("Exec"))
    ET.SubElement(execute, tag("Command")).text = "powershell.exe"
    launcher = str(PureWindowsPath(str(cfg["deployment_output_directory"])) / ARTIFACT_NAMES[0])
    ET.SubElement(execute, tag("Arguments")).text = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy AllSigned -File " + _ps_quote(launcher)
    ET.SubElement(execute, tag("WorkingDirectory")).text = str(cfg["working_directory"])
    ET.indent(root, space="  ")
    rendered: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return rendered + b"\n"


def render(manifest: Mapping[str, Any], output_directory: str | Path) -> dict[str, Any]:
    cfg = validate_manifest(manifest); output = Path(output_directory)
    artifacts = {ARTIFACT_NAMES[0]: render_launcher(cfg), ARTIFACT_NAMES[1]: render_xml(cfg)}
    index = {"schema_version": INDEX_SCHEMA, "manifest_digest": cfg["manifest_digest"],
             "expected_repository_sha": cfg["expected_repository_sha"],
             "artifacts": {name: {"sha256": byte_digest(data), "size": len(data)} for name, data in sorted(artifacts.items())},
             "scheduler_mutation_performed": False, "sensitive_material_embedded": False}
    artifacts[INDEX_NAME] = canonical_json_bytes(index)
    if output.exists() and (not output.is_dir() or output.is_symlink()):
        raise ValueError("deployment_output_unsafe")
    output.mkdir(parents=True, exist_ok=True)
    for name, data in artifacts.items():
        target = output / name
        if target.exists():
            if target.is_symlink() or not target.is_file() or target.read_bytes() != data:
                raise ValueError("conflicting_output:" + name)
        else:
            target.write_bytes(data)
    return {"status": "windows_deployment_ready", "manifest_digest": cfg["manifest_digest"], "output_directory": str(output), "artifact_digests": {n: byte_digest(d) for n, d in sorted(artifacts.items())}, "scheduler_mutation_performed": False}


def verify(manifest: Mapping[str, Any], output_directory: str | Path) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        cfg = validate_manifest(manifest); output = Path(output_directory)
        expected = {ARTIFACT_NAMES[0]: render_launcher(cfg), ARTIFACT_NAMES[1]: render_xml(cfg)}
        index_path = output / INDEX_NAME
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if index.get("manifest_digest") != cfg["manifest_digest"] or index.get("expected_repository_sha") != cfg["expected_repository_sha"]:
            reasons.append("deployment_manifest_digest_mismatch")
        for name, data in expected.items():
            actual = (output / name).read_bytes()
            if actual != data or index.get("artifacts", {}).get(name, {}).get("sha256") != byte_digest(actual): reasons.append(name + "_digest_mismatch")
        launcher = expected[ARTIFACT_NAMES[0]].decode(); xml = expected[ARTIFACT_NAMES[1]].decode()
        if "$arguments = @(" not in launcher or "Invoke-Expression" in launcher or "cmd.exe" in launcher: reasons.append("unsafe_python_invocation")
        if "[DateTimeOffset]::UtcNow" not in launcher: reasons.append("fresh_evaluation_time_missing")
        if launcher.count("$evaluationTime") != 2 or "'--evaluation-time', $evaluationTime" not in launcher: reasons.append("evaluation_time_not_consumed_by_wake")
        tree = ET.fromstring(expected[ARTIFACT_NAMES[1]])
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        if tree.findtext(".//t:MultipleInstancesPolicy", namespaces=ns) != "IgnoreNew": reasons.append("task_concurrency_not_serialized")
        commands = tree.findall(".//t:Actions/t:Exec/t:Command", ns)
        if len(commands) != 1 or commands[0].text != "powershell.exe": reasons.append("task_action_not_launcher_only")
        if SECRET_WORDS.search(launcher + xml + json.dumps(index)): reasons.append("credential_or_secret_material_present")
        if index.get("scheduler_mutation_performed") is not False: reasons.append("scheduler_mutation_not_disclaimed")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, ET.ParseError) as exc:
        reasons.append(str(exc))
    return {"status": "windows_deployment_ready" if not reasons else "windows_deployment_blocked", "reason_codes": sorted(set(reasons)), "scheduler_mutation_performed": False}


def inspect(manifest: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_manifest(manifest)
    return {"status": "windows_deployment_ready", "manifest": cfg, "artifact_names": [*ARTIFACT_NAMES, INDEX_NAME], "scheduler_mutation_performed": False}


def _ps_command(argv: list[str]) -> str:
    return " ".join(_ps_quote(x) for x in argv)


def print_install_command(manifest: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_manifest(manifest); xml = str(PureWindowsPath(str(cfg["deployment_output_directory"])) / ARTIFACT_NAMES[1])
    argv = ["schtasks.exe", "/Create", "/TN", str(cfg["task_name"]), "/XML", xml]
    return {"status": "windows_deployment_ready", "argv": argv, "powershell": "& " + _ps_command(argv), "executed": False, "scheduler_mutation_performed": False}


def print_uninstall_command(manifest: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_manifest(manifest); argv = ["schtasks.exe", "/Delete", "/TN", str(cfg["task_name"]), "/F"]
    return {"status": "windows_deployment_ready", "argv": argv, "powershell": "& " + _ps_command(argv), "executed": False, "scheduler_mutation_performed": False}


def print_preflight_command(manifest: Mapping[str, Any]) -> dict[str, Any]:
    cfg = validate_manifest(manifest); py = str(cfg["python_executable"]); repo = PureWindowsPath(str(cfg["repository_root"])); wake = str(cfg["wake_configuration_path"])
    commands = [
        ["git.exe", "-C", str(repo), "rev-parse", "HEAD"],
        [py, str(repo / "scripts" / "maintenance_loop_activation.py"), "doctor-live", "--config", wake, "--evaluation-time", "<fresh-utc-evaluation-time>"],
        [py, str(repo / "scripts" / "maintenance_wake_cycle.py"), "--config", wake, "--evaluation-time", "$([DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ'))", "doctor"],
        [py, str(repo / "scripts" / "maintenance_wake_cycle.py"), "--config", wake, "--evaluation-time", "$([DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ'))", "wake-once"],
        [py, str(repo / "scripts" / "maintenance_wake_cycle.py"), "--config", wake, "--evaluation-time", "$([DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ'))", "inspect-receipts"],
    ]
    rendered = [{"argv": x, "powershell": "& " + _ps_command(x)} for x in commands]
    for item in rendered[2:]:
        fixed = [str(x) for x in item["argv"]]
        marker = fixed.index("$([DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ'))")
        item["powershell"] = "$evaluationTime = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ'); & " + _ps_command(fixed[:marker]) + " $evaluationTime " + _ps_command(fixed[marker+1:])
    return {"status": "windows_deployment_ready", "expected_repository_sha": cfg["expected_repository_sha"], "commands": rendered, "executed": False, "scheduler_mutation_performed": False}


__all__ = ["MANIFEST_SCHEMA", "INDEX_SCHEMA", "ARTIFACT_NAMES", "INDEX_NAME", "canonical_json_bytes", "validate_manifest", "load_manifest", "template", "render_launcher", "render_xml", "render", "verify", "inspect", "print_install_command", "print_uninstall_command", "print_preflight_command"]

"""Narrow parent adapter for inference in a custody-selected Python runtime."""
from __future__ import annotations

import json
import math
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .local_model import ActiveModelIdentity, ModelLoadError
from .local_model_resource_profile import (
    LocalModelResourceProfileError,
    llama_cpp_constructor_options,
    llama_cpp_resource_profile_digest,
    validate_llama_cpp_resource_profile,
)

MAX_PROTOCOL_BYTES = 65536


def _valid_runtime_resource_seconds(value: object) -> bool:
    if value is None:
        return True
    try:
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(float(value)) and 0 <= float(value) <= 3600)
    except (OverflowError, TypeError, ValueError):
        return False

_WORKER = r'''import hashlib,json,os,sys
import time
PREFIX="SENTIENTOS_LOCAL_MODEL_WORKER="
try:
 import resource
except ImportError:
 resource=None
def resources():
 if resource is None: return {"peak_rss_kib":None,"user_cpu_seconds":None,"system_cpu_seconds":None}
 usage=resource.getrusage(resource.RUSAGE_SELF)
 return {"peak_rss_kib":int(usage.ru_maxrss),"user_cpu_seconds":usage.ru_utime,"system_cpu_seconds":usage.ru_stime}
def generation_resources(before,started):
 after=resources()
 def delta(key):
  old=before.get(key); new=after.get(key)
  if isinstance(old,(int,float)) and isinstance(new,(int,float)): return max(0.0,float(new)-float(old))
  return None
 rss=after.get("peak_rss_kib")
 if isinstance(rss,int): rss_bytes=rss if sys.platform=="darwin" else rss*1024 if sys.platform.startswith("linux") else None
 else: rss_bytes=None
 return {"schema_version":"sentientos.llama_cpp_invocation_resource_observation:v1",
  "user_cpu_seconds":delta("user_cpu_seconds"),"system_cpu_seconds":delta("system_cpu_seconds"),
  "wall_seconds":max(0.0,time.monotonic()-started),"process_peak_rss_bytes":rss_bytes}
def emit(v):
 data=json.dumps(v,sort_keys=True,separators=(",",":"))
 if len(data.encode())>65536: raise RuntimeError("response_too_large")
 print(PREFIX+data,flush=True)
try:
 from llama_cpp import Llama
 path=sys.argv[1]; expected=sys.argv[2]; layers=int(sys.argv[3]); nctx=int(sys.argv[4]); nthreads=int(sys.argv[5]); posture=sys.argv[6]
 profile=json.loads(sys.argv[7]) if len(sys.argv)>7 and sys.argv[7] else None
 if posture not in {"production","rootless_experimental"}: raise RuntimeError("invalid_identity_posture")
 if not 0 <= nthreads <= 256: raise RuntimeError("invalid_thread_limit")
 h=hashlib.sha256(); size=0
 with open(path,"rb") as f:
  while True:
   b=f.read(1048576)
   if not b: break
   h.update(b); size+=len(b)
 if h.hexdigest()!=expected: raise RuntimeError("artifact_identity_mismatch")
 options={"n_ctx":nctx,"n_gpu_layers":layers}
 if profile is not None:
  if (not isinstance(profile,dict) or set(profile)!={"schema_version","profile_id","n_ctx","n_gpu_layers","n_threads","n_threads_batch","n_batch","n_ubatch"}
      or profile.get("schema_version")!="sentientos.llama_cpp_resource_profile:v1"
      or profile.get("n_ctx")!=nctx or profile.get("n_gpu_layers")!=layers): raise RuntimeError("resource_profile_invalid")
  options.update({k:profile[k] for k in ("n_batch","n_ubatch")})
  if profile["n_threads"]: options["n_threads"]=profile["n_threads"]
  if profile["n_threads_batch"]: options["n_threads_batch"]=profile["n_threads_batch"]
 elif nthreads: options["n_threads"]=nthreads
 model=Llama(model_path=path,verbose=False,**options)
 base_threads=int(model.n_threads); base_threads_batch=int(model.n_threads_batch)
 if not (0<=base_threads<=256 and 0<=base_threads_batch<=256): raise RuntimeError("runtime_thread_profile_invalid")
 emit({"type":"ready","interpreter_path":os.path.realpath(sys.executable),"artifact_sha256":h.hexdigest(),"artifact_size_bytes":size,"engine":"llama_cpp","posture":posture,**resources()})
 for line in sys.stdin:
  if len(line.encode())>65536: raise RuntimeError("request_too_large")
  request=json.loads(line)
  if set(request)=={"type"} and request["type"]=="shutdown": emit({"type":"shutdown"}); break
  if set(request)!={"type","prompt","history","generation"} or request["type"]!="generate": raise RuntimeError("malformed_protocol")
  prompt=request["prompt"]; history=request["history"]; generation=request["generation"]
  if not isinstance(prompt,str) or len(prompt)>32768 or not isinstance(history,list): raise RuntimeError("malformed_protocol")
  if not isinstance(generation,dict): raise RuntimeError("malformed_protocol")
  has_thread_ceiling="max_backend_threads" in generation
  thread_ceiling=generation.pop("max_backend_threads",None)
  restore_threads=None
  effective_threads=None
  if has_thread_ceiling:
   if type(thread_ceiling) is not int or not 1<=thread_ceiling<=256: raise RuntimeError("backend_thread_ceiling_invalid")
   set_threads=getattr(__import__("llama_cpp"),"llama_set_n_threads",None)
   context=getattr(model,"ctx",None)
   if not callable(set_threads) or context is None: raise RuntimeError("backend_thread_limit_unavailable")
   effective_threads=min(thread_ceiling,base_threads or thread_ceiling,base_threads_batch or thread_ceiling)
   restore_threads=(set_threads,context,base_threads,base_threads_batch)
  try:
   if restore_threads is not None:
    restore_threads[0](restore_threads[1],effective_threads,effective_threads)
   resource_before=resources(); generation_started=time.monotonic()
   rendered="\n".join([*(str(x) for x in history),prompt])
   max_tokens=min(int(generation.get("max_new_tokens",8)),512)
   temperature=float(generation.get("temperature",0)); top_p=float(generation.get("top_p",1))
   if generation.get("use_model_chat_template") is True:
    context=json.loads(prompt)
    if not isinstance(context,dict) or not isinstance(context.get("instruction"),str): raise RuntimeError("chat_template_context_invalid")
    system_instruction=context.pop("instruction")
    response_format={"type":"json_object"}
    schema=generation.get("structured_output_schema")
    if isinstance(schema,dict): response_format["schema"]=schema
    result=model.create_chat_completion(messages=[{"role":"system","content":system_instruction},{"role":"user","content":json.dumps(context,sort_keys=True,separators=(",",":"))}],max_tokens=max_tokens,temperature=temperature,top_p=top_p,response_format=response_format)
    output=str(result["choices"][0]["message"]["content"])
   else:
    result=model(rendered,max_tokens=max_tokens,temperature=temperature,top_p=top_p)
    output=str(result["choices"][0]["text"])
  finally:
   if restore_threads is not None:
    restore_threads[0](restore_threads[1],restore_threads[2],restore_threads[3])
  if len(output)>32768: raise RuntimeError("response_too_large")
  emit({"type":"generated","output":output,**resources(),
   "invocation_resources":generation_resources(resource_before,generation_started)})
except Exception as exc:
 emit({"type":"error","error_type":type(exc).__name__,"diagnostic":str(exc)[:512]})
 sys.exit(70)
'''


def _environment() -> dict[str, str]:
    denied = {"PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "VIRTUAL_ENV", "CONDA_PREFIX"}
    value = {key: item for key, item in os.environ.items() if key not in denied}
    value.update({"PYTHONDONTWRITEBYTECODE": "1", "NO_PROXY": "*"})
    return value


class ExactRuntimeLocalModel:
    """LocalModel-compatible session whose llama.cpp calls stay in one exact interpreter."""

    supports_per_invocation_thread_limit = True

    def __init__(self, chain: Mapping[str, Any], load: Mapping[str, Any], *, startup_timeout: float = 30,
                 identity_posture: str = "production") -> None:
        if identity_posture not in {"production", "rootless_experimental"}:
            raise ModelLoadError("invalid model identity posture")
        n_threads = int(load.get("n_threads", 0))
        if not 0 <= n_threads <= 256:
            raise ModelLoadError("invalid model thread limit")
        max_new_tokens = int(load.get("max_new_tokens", 8))
        if not 1 <= max_new_tokens <= 512:
            raise ModelLoadError("invalid model generation limit")
        candidate_options = {"gpu_layers": int(load["n_gpu_layers"])}
        profile = load.get("resource_profile")
        profile_json = ""
        if profile is not None:
            try:
                profile = validate_llama_cpp_resource_profile(profile)
            except LocalModelResourceProfileError as exc:
                raise ModelLoadError(str(exc)) from exc
            if (profile["n_ctx"] != int(load["n_ctx"])
                    or profile["n_gpu_layers"] != int(load["n_gpu_layers"])
                    or ("n_threads" in load and load["n_threads"] != profile["n_threads"])
                    or load.get("resource_profile_digest") != llama_cpp_resource_profile_digest(profile)):
                raise ModelLoadError("resource profile does not match the approved load configuration")
            candidate_options["resource_profile_digest"] = load["resource_profile_digest"]
            for name in ("n_threads", "n_threads_batch", "n_batch", "n_ubatch"):
                if profile[name]:
                    candidate_options[name] = profile[name]
            profile_json = json.dumps(profile, sort_keys=True, separators=(",", ":"))
        if n_threads and profile is None:
            candidate_options["n_threads"] = n_threads
        self.config = ModelConfig(
            [ModelCandidate(Path(str(chain["artifact_path"])), "llama_cpp", str(chain["model_id"]),
                            candidate_options)],
            default_engine="llama_cpp", max_context_tokens=int(load["n_ctx"]),
            generation=GenerationConfig(max_new_tokens=max_new_tokens, temperature=0, top_p=1),
        )
        interpreter = Path(str(chain["interpreter_path"])).resolve(strict=True)
        self._process = subprocess.Popen(
            [str(interpreter), "-I", "-u", "-c", _WORKER, str(chain["artifact_path"]),
             str(chain["artifact_sha256"]), str(load["n_gpu_layers"]), str(load["n_ctx"]),
             str(n_threads), identity_posture, profile_json],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            bufsize=1, env=_environment(), cwd=str(Path(str(chain["artifact_path"])).parent),
        )
        self._lock = threading.Lock()
        ready = self._read()
        expected = {"type": "ready", "interpreter_path": str(interpreter),
                    "artifact_sha256": chain["artifact_sha256"],
                    "artifact_size_bytes": chain["artifact_size_bytes"], "engine": "llama_cpp",
                    "posture": identity_posture,
                    "peak_rss_kib": ready.get("peak_rss_kib"),
                    "user_cpu_seconds": ready.get("user_cpu_seconds"),
                    "system_cpu_seconds": ready.get("system_cpu_seconds")}
        if ready != expected:
            self.close()
            raise ModelLoadError("exact runtime worker identity mismatch")
        self.peak_rss_kib = ready["peak_rss_kib"]
        self.user_cpu_seconds = ready["user_cpu_seconds"]
        self.system_cpu_seconds = ready["system_cpu_seconds"]
        candidate = self.config.candidates[0]
        from .local_model import candidate_configuration_digest
        self.active_identity = ActiveModelIdentity(
            engine="llama_cpp", resolved_artifact_path=str(Path(str(chain["artifact_path"])).resolve()),
            semantic_artifact_identity="sha256:" + str(chain["artifact_sha256"]),
            model_content_sha256=str(chain["artifact_sha256"]), artifact_size_bytes=int(chain["artifact_size_bytes"]),
            sidecar_metadata_digest=None,
            configuration_digest=candidate_configuration_digest(candidate, self.config, "llama_cpp"),
            candidate_index=0, posture=identity_posture, fallback=False,
        )

    def _read(self) -> dict[str, Any]:
        assert self._process.stdout is not None
        line = self._process.stdout.readline(MAX_PROTOCOL_BYTES + 1)
        prefix = "SENTIENTOS_LOCAL_MODEL_WORKER="
        if not line or len(line.encode()) > MAX_PROTOCOL_BYTES or not line.startswith(prefix):
            raise ModelLoadError("exact runtime worker protocol unavailable")
        value = json.loads(line[len(prefix):])
        if value.get("type") == "error":
            raise ModelLoadError("exact runtime worker failed: " + str(value.get("diagnostic", "unknown")))
        return cast(dict[str, Any], value)

    def generate(self, prompt: str, history: Sequence[str] | None = None, **generation: Any) -> str:
        return self.generate_with_metadata(prompt, history, **generation)[0]

    def generate_with_metadata(self, prompt: str, history: Sequence[str] | None = None,
                               **generation: Any) -> tuple[str, dict[str, Any]]:
        if self._process.poll() is not None:
            raise ModelLoadError("exact runtime worker exited; explicit reload required")
        if "max_backend_threads" in generation and (
                type(generation["max_backend_threads"]) is not int
                or not 1 <= generation["max_backend_threads"] <= 256):
            raise ModelLoadError("invalid per-invocation backend thread limit")
        request = {"type": "generate", "prompt": prompt, "history": list(history or ()), "generation": generation}
        data = json.dumps(request, sort_keys=True, separators=(",", ":"))
        if len(data.encode()) > MAX_PROTOCOL_BYTES:
            raise ModelLoadError("exact runtime worker request too large")
        with self._lock:
            assert self._process.stdin is not None
            self._process.stdin.write(data + "\n"); self._process.stdin.flush()
            response = self._read()
        if (set(response) != {"type", "output", "peak_rss_kib", "user_cpu_seconds",
                              "system_cpu_seconds", "invocation_resources"}
                or response["type"] != "generated" or not isinstance(response["output"], str)):
            raise ModelLoadError("exact runtime worker malformed response")
        resources = response["invocation_resources"]
        if not isinstance(resources, Mapping) or set(resources) != {
                "schema_version", "user_cpu_seconds", "system_cpu_seconds", "wall_seconds",
                "process_peak_rss_bytes"} or resources.get("schema_version") != (
                    "sentientos.llama_cpp_invocation_resource_observation:v1"):
            raise ModelLoadError("exact runtime worker resource observation malformed")
        for key in ("user_cpu_seconds", "system_cpu_seconds", "wall_seconds"):
            value = resources.get(key)
            if not _valid_runtime_resource_seconds(value):
                raise ModelLoadError("exact runtime worker resource observation malformed")
        rss_bytes = resources.get("process_peak_rss_bytes")
        if rss_bytes is not None and (type(rss_bytes) is not int or not 0 <= rss_bytes <= 1_099_511_627_776):
            raise ModelLoadError("exact runtime worker resource observation malformed")
        self.peak_rss_kib = response["peak_rss_kib"]
        self.user_cpu_seconds = response["user_cpu_seconds"]
        self.system_cpu_seconds = response["system_cpu_seconds"]
        completion = {
            "schema_version": "sentientos.llama_cpp_completion_observation:v2",
            "backend": "llama_cpp",
            "finish_reason": "unknown",
            "completion_tokens": None,
            "prompt_tokens": None,
            "token_limit_reached": None,
            "invocation_resources": dict(resources),
        }
        return response["output"], completion

    def generate_governed_with_metadata(self, prompt: str, **generation: Any
            ) -> tuple[str, dict[str, Any]]:
        """Return output plus the exact worker's bounded per-invocation measurements."""
        return self.generate_with_metadata(prompt, (), **generation)

    def generate_governed(self, prompt: str, **generation: Any) -> str:
        """Compatibility path for callers that do not consume backend metadata."""
        return self.generate_governed_with_metadata(prompt, **generation)[0]

    def describe(self) -> str:
        return "llama_cpp exact-runtime worker (" + str(self.active_identity.resolved_artifact_path) + ")"

    def cancel_pending_generation(self) -> None:
        """Terminate the isolated runtime process so invocation deadlines can hold."""
        if self._process.poll() is None:
            self._process.kill()
            self._process.wait(timeout=5)

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                assert self._process.stdin is not None
                self._process.stdin.write('{"type":"shutdown"}\n'); self._process.stdin.flush()
                self._process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                self._process.kill(); self._process.wait()

    def __del__(self) -> None:
        try: self.close()
        except Exception: pass

"""Narrow parent adapter for inference in a custody-selected Python runtime."""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from .config import GenerationConfig, ModelCandidate, ModelConfig
from .local_model import ActiveModelIdentity, ModelLoadError

MAX_PROTOCOL_BYTES = 65536

_WORKER = r'''import hashlib,json,os,sys
PREFIX="SENTIENTOS_LOCAL_MODEL_WORKER="
def emit(v):
 data=json.dumps(v,sort_keys=True,separators=(",",":"))
 if len(data.encode())>65536: raise RuntimeError("response_too_large")
 print(PREFIX+data,flush=True)
try:
 from llama_cpp import Llama
 path=sys.argv[1]; expected=sys.argv[2]; layers=int(sys.argv[3]); nctx=int(sys.argv[4])
 h=hashlib.sha256(); size=0
 with open(path,"rb") as f:
  while True:
   b=f.read(1048576)
   if not b: break
   h.update(b); size+=len(b)
 if h.hexdigest()!=expected: raise RuntimeError("artifact_identity_mismatch")
 model=Llama(model_path=path,n_ctx=nctx,n_gpu_layers=layers,verbose=False)
 emit({"type":"ready","interpreter_path":os.path.realpath(sys.executable),"artifact_sha256":h.hexdigest(),"artifact_size_bytes":size,"engine":"llama_cpp"})
 for line in sys.stdin:
  if len(line.encode())>65536: raise RuntimeError("request_too_large")
  request=json.loads(line)
  if set(request)=={"type"} and request["type"]=="shutdown": emit({"type":"shutdown"}); break
  if set(request)!={"type","prompt","history","generation"} or request["type"]!="generate": raise RuntimeError("malformed_protocol")
  prompt=request["prompt"]; history=request["history"]; generation=request["generation"]
  if not isinstance(prompt,str) or len(prompt)>32768 or not isinstance(history,list): raise RuntimeError("malformed_protocol")
  rendered="\n".join([*(str(x) for x in history),prompt])
  result=model(rendered,max_tokens=min(int(generation.get("max_new_tokens",8)),512),temperature=float(generation.get("temperature",0)),top_p=float(generation.get("top_p",1)))
  output=str(result["choices"][0]["text"])
  if len(output)>32768: raise RuntimeError("response_too_large")
  emit({"type":"generated","output":output})
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

    def __init__(self, chain: Mapping[str, Any], load: Mapping[str, Any], *, startup_timeout: float = 30) -> None:
        self.config = ModelConfig(
            [ModelCandidate(Path(str(chain["artifact_path"])), "llama_cpp", str(chain["model_id"]),
                            {"gpu_layers": int(load["n_gpu_layers"])})],
            default_engine="llama_cpp", max_context_tokens=int(load["n_ctx"]),
            generation=GenerationConfig(max_new_tokens=8, temperature=0, top_p=1),
        )
        interpreter = Path(str(chain["interpreter_path"])).resolve(strict=True)
        self._process = subprocess.Popen(
            [str(interpreter), "-I", "-u", "-c", _WORKER, str(chain["artifact_path"]),
             str(chain["artifact_sha256"]), str(load["n_gpu_layers"]), str(load["n_ctx"])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            bufsize=1, env=_environment(), cwd=str(Path(str(chain["artifact_path"])).parent),
        )
        self._lock = threading.Lock()
        ready = self._read()
        expected = {"type": "ready", "interpreter_path": str(interpreter),
                    "artifact_sha256": chain["artifact_sha256"],
                    "artifact_size_bytes": chain["artifact_size_bytes"], "engine": "llama_cpp"}
        if ready != expected:
            self.close()
            raise ModelLoadError("exact runtime worker identity mismatch")
        candidate = self.config.candidates[0]
        from .local_model import candidate_configuration_digest
        self.active_identity = ActiveModelIdentity(
            engine="llama_cpp", resolved_artifact_path=str(Path(str(chain["artifact_path"])).resolve()),
            semantic_artifact_identity="sha256:" + str(chain["artifact_sha256"]),
            model_content_sha256=str(chain["artifact_sha256"]), artifact_size_bytes=int(chain["artifact_size_bytes"]),
            sidecar_metadata_digest=None,
            configuration_digest=candidate_configuration_digest(candidate, self.config, "llama_cpp"),
            candidate_index=0, posture="production", fallback=False,
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
        if self._process.poll() is not None:
            raise ModelLoadError("exact runtime worker exited; explicit reload required")
        request = {"type": "generate", "prompt": prompt, "history": list(history or ()), "generation": generation}
        data = json.dumps(request, sort_keys=True, separators=(",", ":"))
        if len(data.encode()) > MAX_PROTOCOL_BYTES:
            raise ModelLoadError("exact runtime worker request too large")
        with self._lock:
            assert self._process.stdin is not None
            self._process.stdin.write(data + "\n"); self._process.stdin.flush()
            response = self._read()
        if set(response) != {"type", "output"} or response["type"] != "generated" or not isinstance(response["output"], str):
            raise ModelLoadError("exact runtime worker malformed response")
        return response["output"]

    def describe(self) -> str:
        return "llama_cpp exact-runtime worker (" + str(self.active_identity.resolved_artifact_path) + ")"

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

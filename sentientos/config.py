from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    import yaml
except ModuleNotFoundError:  # pragma: no cover - environment fallback
    yaml = None  # type: ignore[assignment]

from .storage import get_data_root

_CONFIG_ENV = "SENTIENTOS_CONFIG"

LOGGER = logging.getLogger(__name__)

_MODEL_CONFIG_ENV = "SENTIENTOS_MODEL_CONFIG"
_MODEL_PATH_ENV = "SENTIENTOS_MODEL_PATH"
_MODEL_FALLBACKS_ENV = "SENTIENTOS_MODEL_FALLBACKS"
_MODEL_ENGINE_ENV = "SENTIENTOS_MODEL_ENGINE"
_MODEL_CTX_ENV = "SENTIENTOS_MODEL_CTX"
_MODEL_MAX_NEW_TOKENS_ENV = "SENTIENTOS_MODEL_MAX_NEW_TOKENS"
_MODEL_TEMPERATURE_ENV = "SENTIENTOS_MODEL_TEMPERATURE"
_MODEL_TOP_P_ENV = "SENTIENTOS_MODEL_TOP_P"
_MODEL_TOP_K_ENV = "SENTIENTOS_MODEL_TOP_K"
_MODEL_REPETITION_ENV = "SENTIENTOS_MODEL_REPETITION_PENALTY"


@dataclass
class GenerationConfig:
    """Default sampling parameters for local generation."""

    max_new_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: Optional[int] = None
    repetition_penalty: Optional[float] = None

    def as_kwargs(self, **overrides: Any) -> Dict[str, Any]:
        """Return a merged dictionary of sampling parameters."""

        params: Dict[str, Any] = {
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repetition_penalty": self.repetition_penalty,
        }
        for key, value in overrides.items():
            if value is None:
                continue
            params[key] = value
        return params


@dataclass
class ModelCandidate:
    """A concrete local model candidate that can be loaded."""

    path: Optional[Path]
    engine: str = "auto"
    name: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)

    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.path is not None:
            return str(self.path)
        return self.engine


@dataclass
class ModelConfig:
    """Runtime configuration describing available local language models."""

    candidates: List[ModelCandidate]
    default_engine: str = "auto"
    max_context_tokens: int = 4096
    generation: GenerationConfig = field(default_factory=GenerationConfig)


def load_model_config() -> ModelConfig:
    """Load the runtime model configuration from disk or environment."""

    config_path = os.environ.get(_MODEL_CONFIG_ENV)
    data_root = get_data_root()
    if config_path:
        config_file = Path(config_path)
        if config_file.exists():
            try:
                raw = json.loads(config_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                LOGGER.warning("Invalid model configuration file %s: %s", config_file, exc)
            else:
                return _parse_config_mapping(raw, data_root)
        else:
            LOGGER.warning("Model configuration file %s does not exist", config_file)
    return _default_config(data_root)


def _parse_config_mapping(mapping: Dict[str, Any], data_root: Path) -> ModelConfig:
    candidates = [
        _parse_candidate(candidate, data_root)
        for candidate in mapping.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    if not candidates:
        candidates = _default_candidates(data_root)

    default_engine = str(mapping.get("default_engine", "auto"))
    max_context_tokens = int(mapping.get("max_context_tokens", 4096))
    generation = _parse_generation(mapping.get("generation", {}))

    return ModelConfig(
        candidates=candidates,
        default_engine=default_engine,
        max_context_tokens=max_context_tokens,
        generation=generation,
    )


def _parse_candidate(candidate: Dict[str, Any], data_root: Path) -> ModelCandidate:
    path_value = candidate.get("path")
    path: Optional[Path]
    if path_value is None:
        path = None
    else:
        resolved = Path(path_value)
        if not resolved.is_absolute():
            resolved = data_root / resolved
        path = resolved
    engine = str(candidate.get("engine", "auto"))
    name = candidate.get("name")
    options = candidate.get("options")
    if not isinstance(options, dict):
        options = {}
    return ModelCandidate(path=path, engine=engine, name=name, options=options)


def _parse_generation(mapping: Dict[str, Any]) -> GenerationConfig:
    generation = GenerationConfig()
    if "max_new_tokens" in mapping:
        generation.max_new_tokens = int(mapping["max_new_tokens"])
    if "temperature" in mapping:
        generation.temperature = float(mapping["temperature"])
    if "top_p" in mapping:
        generation.top_p = float(mapping["top_p"])
    if "top_k" in mapping:
        value = mapping["top_k"]
        generation.top_k = None if value is None else int(value)
    if "repetition_penalty" in mapping:
        value = mapping["repetition_penalty"]
        generation.repetition_penalty = None if value is None else float(value)
    return generation


def _default_config(data_root: Path) -> ModelConfig:
    candidates = _default_candidates(data_root)
    default_engine = os.environ.get(_MODEL_ENGINE_ENV, "auto")
    max_context_tokens = _env_int(_MODEL_CTX_ENV, 4096)
    generation = GenerationConfig(
        max_new_tokens=_env_int(_MODEL_MAX_NEW_TOKENS_ENV, 512),
        temperature=_env_float(_MODEL_TEMPERATURE_ENV, 0.7),
        top_p=_env_float(_MODEL_TOP_P_ENV, 0.95),
        top_k=_env_optional_int(_MODEL_TOP_K_ENV),
        repetition_penalty=_env_optional_float(_MODEL_REPETITION_ENV),
    )
    return ModelConfig(
        candidates=candidates,
        default_engine=default_engine,
        max_context_tokens=max_context_tokens,
        generation=generation,
    )


def _default_candidates(data_root: Path) -> List[ModelCandidate]:
    candidates: List[ModelCandidate] = []
    default_path = os.environ.get(_MODEL_PATH_ENV) or os.environ.get("LOCAL_MODEL_PATH")
    if default_path:
        base_path = Path(default_path)
        if not base_path.is_absolute():
            base_path = data_root / base_path
    else:
        base_path = (
            data_root
            / "models"
            / "mixtral-8x7b"
            / "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"
        )
    candidates.append(
        ModelCandidate(
            path=base_path,
            engine=os.environ.get(_MODEL_ENGINE_ENV, "auto"),
            name="Mixtral-8x7B Instruct (GGUF)",
        )
    )

    fallback_env = os.environ.get(_MODEL_FALLBACKS_ENV)
    if fallback_env:
        for entry in fallback_env.split(os.pathsep):
            entry = entry.strip()
            if not entry:
                continue
            fallback_path = Path(entry)
            if not fallback_path.is_absolute():
                fallback_path = data_root / fallback_path
            candidates.append(
                ModelCandidate(
                    path=fallback_path,
                    engine="auto",
                )
            )

    default_fallback = data_root / "models" / "gpt-oss-13b"
    if all(candidate.path != default_fallback for candidate in candidates):
        candidates.append(ModelCandidate(path=default_fallback, engine="auto", name="gpt-oss-13b"))
    # Legacy GPT-OSS 120B builds require extreme hardware and must be configured manually.
    return candidates


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid integer for %s: %s", name, value)
        return default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid float for %s: %s", name, value)
        return default


def _env_optional_int(name: str) -> Optional[int]:
    value = os.environ.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid integer for %s: %s", name, value)
        return None


def _env_optional_float(name: str) -> Optional[float]:
    value = os.environ.get(name)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid float for %s: %s", name, value)
        return None


@dataclass
class ForgettingCurveConfig:
    half_life_days: float = 30.0
    min_keep_score: float = 0.25


@dataclass
class MemoryCuratorConfig:
    enable: bool = False
    rollup_interval_s: int = 900
    max_capsule_len: int = 4096
    forgetting_curve: ForgettingCurveConfig = field(default_factory=ForgettingCurveConfig)


@dataclass
class MemoryConfig:
    curator: MemoryCuratorConfig = field(default_factory=MemoryCuratorConfig)


@dataclass
class ReflexionConfig:
    enable: bool = False
    max_tokens: int = 2048
    store_path: Optional[Path] = None


@dataclass
class CriticFactCheckConfig:
    enable: bool = False
    timeout_s: float = 5.0


@dataclass
class CriticConfig:
    enable: bool = False
    policy: str = "standard"
    factcheck: CriticFactCheckConfig = field(default_factory=CriticFactCheckConfig)


@dataclass
class CouncilConfig:
    enable: bool = False
    members: Tuple[str, ...] = ("curator", "critic", "oracle")
    quorum: int = 2
    tie_breaker: str = "chair"


@dataclass
class OracleConfig:
    enable: bool = False
    provider: Optional[str] = None
    endpoint: Optional[str] = None
    timeout_s: float = 8.0
    budget_per_cycle: float = 0.0


@dataclass
class GoalsCuratorConfig:
    enable: bool = False
    min_support_count: int = 3
    min_days_between_auto_goals: float = 7.0
    max_concurrent_auto_goals: int = 1


@dataclass
class GoalsConfig:
    curator: GoalsCuratorConfig = field(default_factory=GoalsCuratorConfig)


@dataclass
class HungryEyesActiveLearningConfig:
    enable: bool = False
    retrain_every_n_events: int = 25
    max_corpus_mb: int = 32
    seed: Optional[int] = None


@dataclass
class HungryEyesConfig:
    active_learning: HungryEyesActiveLearningConfig = field(default_factory=HungryEyesActiveLearningConfig)


@dataclass
class DeterminismConfig:
    seed: Optional[int] = 1337


@dataclass
class ReflexionBudgetConfig:
    max_per_hour: int = 0


@dataclass
class OracleBudgetConfig:
    max_requests_per_day: int = 0


@dataclass
class GoalsBudgetConfig:
    max_autocreated_per_day: int = 0


@dataclass
class BudgetsConfig:
    reflexion: ReflexionBudgetConfig = field(default_factory=ReflexionBudgetConfig)
    oracle: OracleBudgetConfig = field(default_factory=OracleBudgetConfig)
    goals: GoalsBudgetConfig = field(default_factory=GoalsBudgetConfig)


@dataclass
class RuntimeConfig:
    determinism: DeterminismConfig = field(default_factory=DeterminismConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    reflexion: ReflexionConfig = field(default_factory=ReflexionConfig)
    critic: CriticConfig = field(default_factory=CriticConfig)
    council: CouncilConfig = field(default_factory=CouncilConfig)
    oracle: OracleConfig = field(default_factory=OracleConfig)
    goals: GoalsConfig = field(default_factory=GoalsConfig)
    hungry_eyes: HungryEyesConfig = field(default_factory=HungryEyesConfig)
    budgets: BudgetsConfig = field(default_factory=BudgetsConfig)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "RuntimeConfig":
        determinism_section = mapping.get("determinism", {})
        determinism = DeterminismConfig(
            seed=_as_optional_int(determinism_section.get("seed"))
        )

        memory_section = mapping.get("memory", {})
        curator_section = _as_mapping(memory_section.get("curator"))
        forgetting_section = _as_mapping(curator_section.get("forgetting_curve"))
        memory = MemoryConfig(
            curator=MemoryCuratorConfig(
                enable=bool(curator_section.get("enable", False)),
                rollup_interval_s=int(curator_section.get("rollup_interval_s", 900)),
                max_capsule_len=int(curator_section.get("max_capsule_len", 4096)),
                forgetting_curve=ForgettingCurveConfig(
                    half_life_days=float(
                        forgetting_section.get("half_life_days", 30.0)
                    ),
                    min_keep_score=float(
                        forgetting_section.get("min_keep_score", 0.25)
                    ),
                ),
            )
        )

        reflexion_section = mapping.get("reflexion", {})
        store_path_value = reflexion_section.get("store_path")
        reflexion_store = None
        if isinstance(store_path_value, str) and store_path_value:
            reflexion_store = Path(store_path_value)
        reflexion = ReflexionConfig(
            enable=bool(reflexion_section.get("enable", False)),
            max_tokens=int(reflexion_section.get("max_tokens", 2048)),
            store_path=reflexion_store,
        )

        critic_section = mapping.get("critic", {})
        factcheck_section = _as_mapping(critic_section.get("factcheck"))
        critic = CriticConfig(
            enable=bool(critic_section.get("enable", False)),
            policy=str(critic_section.get("policy", "standard")),
            factcheck=CriticFactCheckConfig(
                enable=bool(factcheck_section.get("enable", False)),
                timeout_s=float(factcheck_section.get("timeout_s", 5.0)),
            ),
        )

        council_section = mapping.get("council", {})
        members = _as_sequence(council_section.get("members")) or (
            "curator",
            "critic",
            "oracle",
        )
        council = CouncilConfig(
            enable=bool(council_section.get("enable", False)),
            members=tuple(str(member) for member in members),
            quorum=int(council_section.get("quorum", max(1, len(members) // 2 + 1))),
            tie_breaker=str(council_section.get("tie_breaker", "chair")),
        )

        oracle_section = mapping.get("oracle", {})
        oracle = OracleConfig(
            enable=bool(oracle_section.get("enable", False)),
            provider=_as_optional_str(oracle_section.get("provider")),
            endpoint=_as_optional_str(oracle_section.get("endpoint")),
            timeout_s=float(oracle_section.get("timeout_s", 8.0)),
            budget_per_cycle=float(oracle_section.get("budget_per_cycle", 0.0)),
        )

        goals_section = mapping.get("goals", {})
        curator_goal_section = _as_mapping(goals_section.get("curator"))
        goals = GoalsConfig(
            curator=GoalsCuratorConfig(
                enable=bool(curator_goal_section.get("enable", False)),
                min_support_count=int(
                    curator_goal_section.get("min_support_count", 3)
                ),
                min_days_between_auto_goals=float(
                    curator_goal_section.get("min_days_between_auto_goals", 7.0)
                ),
                max_concurrent_auto_goals=int(
                    curator_goal_section.get("max_concurrent_auto_goals", 1)
                ),
            )
        )

        hungry_section = mapping.get("hungry_eyes", {})
        active_section = _as_mapping(hungry_section.get("active_learning"))
        hungry_eyes = HungryEyesConfig(
            active_learning=HungryEyesActiveLearningConfig(
                enable=bool(active_section.get("enable", False)),
                retrain_every_n_events=int(
                    active_section.get("retrain_every_n_events", 25)
                ),
                max_corpus_mb=int(active_section.get("max_corpus_mb", 32)),
                seed=_as_optional_int(active_section.get("seed")),
            )
        )

        budgets_section = mapping.get("budgets", {})
        reflexion_budget_section = _as_mapping(budgets_section.get("reflexion"))
        oracle_budget_section = _as_mapping(budgets_section.get("oracle"))
        goals_budget_section = _as_mapping(budgets_section.get("goals"))
        budgets = BudgetsConfig(
            reflexion=ReflexionBudgetConfig(
                max_per_hour=int(reflexion_budget_section.get("max_per_hour", 0) or 0)
            ),
            oracle=OracleBudgetConfig(
                max_requests_per_day=int(
                    oracle_budget_section.get("max_requests_per_day", 0) or 0
                )
            ),
            goals=GoalsBudgetConfig(
                max_autocreated_per_day=int(
                    goals_budget_section.get("max_autocreated_per_day", 0) or 0
                )
            ),
        )

        return cls(
            determinism=determinism,
            memory=memory,
            reflexion=reflexion,
            critic=critic,
            council=council,
            oracle=oracle,
            goals=goals,
            hungry_eyes=hungry_eyes,
            budgets=budgets,
        )


def load_runtime_config() -> RuntimeConfig:
    """Load the SentientOS autonomy runtime configuration."""

    base = _default_runtime_mapping()
    file_mapping = _load_yaml_config()
    if file_mapping:
        base = _deep_merge(base, file_mapping)
    base = _apply_env_overrides(base)
    return RuntimeConfig.from_mapping(base)


def _load_yaml_config() -> Dict[str, Any]:
    if yaml is None:
        LOGGER.warning("PyYAML missing; skipping config.yaml overrides")
        return {}
    path_env = os.environ.get(_CONFIG_ENV)
    candidates: List[Path] = []
    if path_env:
        candidates.append(Path(path_env))
    candidates.append(Path.cwd() / "config.yaml")
    candidates.append(get_data_root() / "config.yaml")
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            LOGGER.warning("Failed reading config %s: %s", candidate, exc)
            continue
        try:
            loaded = yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            LOGGER.warning("Invalid YAML in %s: %s", candidate, exc)
            continue
        if isinstance(loaded, Mapping):
            return dict(loaded)
    return {}


def _default_runtime_mapping() -> Dict[str, Any]:
    return {
        "determinism": {"seed": 1337},
        "memory": {
            "curator": {
                "enable": False,
                "rollup_interval_s": 900,
                "max_capsule_len": 4096,
                "forgetting_curve": {
                    "half_life_days": 30.0,
                    "min_keep_score": 0.25,
                },
            }
        },
        "reflexion": {"enable": False, "max_tokens": 2048, "store_path": None},
        "critic": {
            "enable": False,
            "policy": "standard",
            "factcheck": {"enable": False, "timeout_s": 5.0},
        },
        "council": {
            "enable": False,
            "members": ["curator", "critic", "oracle"],
            "quorum": 2,
            "tie_breaker": "chair",
        },
        "oracle": {
            "enable": False,
            "provider": None,
            "endpoint": None,
            "timeout_s": 8.0,
            "budget_per_cycle": 0.0,
        },
        "goals": {
            "curator": {
                "enable": False,
                "min_support_count": 3,
                "min_days_between_auto_goals": 7.0,
                "max_concurrent_auto_goals": 1,
            }
        },
        "hungry_eyes": {
            "active_learning": {
                "enable": False,
                "retrain_every_n_events": 25,
                "max_corpus_mb": 32,
                "seed": None,
            }
        },
        "budgets": {
            "reflexion": {"max_per_hour": 0},
            "oracle": {"max_requests_per_day": 0},
            "goals": {"max_autocreated_per_day": 0},
        },
    }


def _deep_merge(base: Dict[str, Any], updates: Mapping[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _apply_env_overrides(mapping: Dict[str, Any]) -> Dict[str, Any]:
    for env_name, (path, converter) in _ENVIRONMENT_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        try:
            value = converter(raw)
        except ValueError:
            LOGGER.warning("Invalid value for %s: %s", env_name, raw)
            continue
        _assign_mapping_value(mapping, path, value)
    return mapping


def _assign_mapping_value(mapping: Dict[str, Any], path: Sequence[str], value: Any) -> None:
    target = mapping
    for key in path[:-1]:
        current = target.get(key)
        if not isinstance(current, dict):
            current = {}
            target[key] = current
        target = current
    target[path[-1]] = value


def _as_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Tuple[Any, ...]:
    if isinstance(value, (list, tuple, set)):
        return tuple(value)
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    return tuple()


def _as_optional_str(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)


def _as_optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(value)


def _to_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on", "enabled"}:
        return True
    if lowered in {"0", "false", "no", "off", "disabled"}:
        return False
    raise ValueError(value)


def _to_int(value: str) -> int:
    return int(value, 10)


def _to_float(value: str) -> float:
    return float(value)


def _to_list(value: str) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


_ENVIRONMENT_OVERRIDES: Dict[str, Tuple[Tuple[str, ...], Any]] = {
    "SENTIENTOS_SEED": (("determinism", "seed"), _to_int),
    "SENTIENTOS_MEMORY_CURATOR_ENABLE": (("memory", "curator", "enable"), _to_bool),
    "SENTIENTOS_MEMORY_CURATOR_ROLLUP_INTERVAL_S": ((
        "memory",
        "curator",
        "rollup_interval_s",
    ), _to_int),
    "SENTIENTOS_MEMORY_CURATOR_MAX_CAPSULE_LEN": ((
        "memory",
        "curator",
        "max_capsule_len",
    ), _to_int),
    "SENTIENTOS_MEMORY_CURATOR_FORGETTING_CURVE_HALF_LIFE_DAYS": ((
        "memory",
        "curator",
        "forgetting_curve",
        "half_life_days",
    ), _to_float),
    "SENTIENTOS_MEMORY_CURATOR_FORGETTING_CURVE_MIN_KEEP_SCORE": ((
        "memory",
        "curator",
        "forgetting_curve",
        "min_keep_score",
    ), _to_float),
    "SENTIENTOS_REFLEXION_ENABLE": (("reflexion", "enable"), _to_bool),
    "SENTIENTOS_REFLEXION_MAX_TOKENS": (("reflexion", "max_tokens"), _to_int),
    "SENTIENTOS_REFLEXION_STORE_PATH": (("reflexion", "store_path"), str),
    "SENTIENTOS_CRITIC_ENABLE": (("critic", "enable"), _to_bool),
    "SENTIENTOS_CRITIC_POLICY": (("critic", "policy"), str),
    "SENTIENTOS_CRITIC_FACTCHECK_ENABLE": ((
        "critic",
        "factcheck",
        "enable",
    ), _to_bool),
    "SENTIENTOS_CRITIC_FACTCHECK_TIMEOUT_S": ((
        "critic",
        "factcheck",
        "timeout_s",
    ), _to_float),
    "SENTIENTOS_COUNCIL_ENABLE": (("council", "enable"), _to_bool),
    "SENTIENTOS_COUNCIL_MEMBERS": (("council", "members"), _to_list),
    "SENTIENTOS_COUNCIL_QUORUM": (("council", "quorum"), _to_int),
    "SENTIENTOS_COUNCIL_TIE_BREAKER": (("council", "tie_breaker"), str),
    "SENTIENTOS_ORACLE_ENABLE": (("oracle", "enable"), _to_bool),
    "SENTIENTOS_ORACLE_PROVIDER": (("oracle", "provider"), str),
    "SENTIENTOS_ORACLE_ENDPOINT": (("oracle", "endpoint"), str),
    "SENTIENTOS_ORACLE_TIMEOUT_S": (("oracle", "timeout_s"), _to_float),
    "SENTIENTOS_ORACLE_BUDGET_PER_CYCLE": (("oracle", "budget_per_cycle"), _to_float),
    "SENTIENTOS_GOALS_CURATOR_ENABLE": ((
        "goals",
        "curator",
        "enable",
    ), _to_bool),
    "SENTIENTOS_GOALS_CURATOR_MIN_SUPPORT_COUNT": ((
        "goals",
        "curator",
        "min_support_count",
    ), _to_int),
    "SENTIENTOS_GOALS_CURATOR_MIN_DAYS_BETWEEN_AUTO_GOALS": ((
        "goals",
        "curator",
        "min_days_between_auto_goals",
    ), _to_float),
    "SENTIENTOS_GOALS_CURATOR_MAX_CONCURRENT_AUTO_GOALS": ((
        "goals",
        "curator",
        "max_concurrent_auto_goals",
    ), _to_int),
    "SENTIENTOS_HUNGRY_EYES_ACTIVE_LEARNING_ENABLE": ((
        "hungry_eyes",
        "active_learning",
        "enable",
    ), _to_bool),
    "SENTIENTOS_HUNGRY_EYES_ACTIVE_LEARNING_RETRAIN_EVERY_N_EVENTS": ((
        "hungry_eyes",
        "active_learning",
        "retrain_every_n_events",
    ), _to_int),
    "SENTIENTOS_HUNGRY_EYES_ACTIVE_LEARNING_MAX_CORPUS_MB": ((
        "hungry_eyes",
        "active_learning",
        "max_corpus_mb",
    ), _to_int),
    "SENTIENTOS_HUNGRY_EYES_ACTIVE_LEARNING_SEED": ((
        "hungry_eyes",
        "active_learning",
        "seed",
    ), _to_int),
    "SENTIENTOS_BUDGET_REFLEXION_MAX_PER_HOUR": ((
        "budgets",
        "reflexion",
        "max_per_hour",
    ), _to_int),
    "SENTIENTOS_BUDGET_ORACLE_MAX_REQUESTS_PER_DAY": ((
        "budgets",
        "oracle",
        "max_requests_per_day",
    ), _to_int),
    "SENTIENTOS_BUDGET_GOALS_MAX_AUTOCREATED_PER_DAY": ((
        "budgets",
        "goals",
        "max_autocreated_per_day",
    ), _to_int),
}

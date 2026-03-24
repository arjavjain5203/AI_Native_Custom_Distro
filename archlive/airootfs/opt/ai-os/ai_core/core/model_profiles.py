"""RAM-tiered model bundle selection for the installer and runtime checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ROLE_ORDER = ("intent", "planning", "coding", "analysis")


def _gib_to_kib(value: float) -> int:
    return int(value * 1024 * 1024)


MODEL_STORAGE_KIB = {
    "phi3:mini": _gib_to_kib(2.2),
    "phi3": _gib_to_kib(2.2),
    "gemma:2b": _gib_to_kib(1.6),
    "mistral:7b": _gib_to_kib(4.4),
    "qwen2.5-coder:1.5b": _gib_to_kib(1.7),
    "qwen2.5-coder:7b": _gib_to_kib(4.7),
    "qwen2.5-coder:14b": _gib_to_kib(9.0),
    "qwen2.5-coder:32b": _gib_to_kib(19.0),
    "codellama:7b": _gib_to_kib(4.0),
    "codellama:13b": _gib_to_kib(7.5),
    "codellama:34b": _gib_to_kib(19.5),
    "mixtral:8x7b": _gib_to_kib(26.0),
    "deepseek-v2:16b": _gib_to_kib(10.5),
}
DEFAULT_MODEL_STORAGE_KIB = _gib_to_kib(2.0)


@dataclass(frozen=True, slots=True)
class ModelProfile:
    key: str
    tier: str
    label: str
    description: str
    models: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "tier": self.tier,
            "label": self.label,
            "description": self.description,
            "models": dict(self.models),
            "unique_models": unique_models(self.models),
            "required_storage_kib": estimate_model_storage_kib(unique_models(self.models)),
        }


PROFILES = {
    "low_end_recommended": ModelProfile(
        key="low_end_recommended",
        tier="low_end",
        label="Low-end recommended",
        description="<= 8 GB RAM quick setup with small intent/planning models and a lightweight coder.",
        models={
            "intent": "phi3:mini",
            "planning": "gemma:2b",
            "coding": "qwen2.5-coder:1.5b",
            "analysis": "gemma:2b",
        },
    ),
    "low_end_alternative": ModelProfile(
        key="low_end_alternative",
        tier="low_end",
        label="Low-end alternative",
        description="<= 8 GB RAM alternative bundle using Gemma for intent and CodeLlama for coding.",
        models={
            "intent": "gemma:2b",
            "planning": "gemma:2b",
            "coding": "codellama:7b",
            "analysis": "gemma:2b",
        },
    ),
    "mid_range_recommended": ModelProfile(
        key="mid_range_recommended",
        tier="mid_range",
        label="Mid-range recommended",
        description="8-16 GB RAM bundle with Phi-3 intent, Mistral planning, and Qwen coder defaults.",
        models={
            "intent": "phi3",
            "planning": "mistral:7b",
            "coding": "qwen2.5-coder:7b",
            "analysis": "mistral:7b",
        },
    ),
    "mid_range_alternative": ModelProfile(
        key="mid_range_alternative",
        tier="mid_range",
        label="Mid-range alternative",
        description="8-16 GB RAM alternative bundle using Gemma for intent and CodeLlama for coding.",
        models={
            "intent": "gemma:2b",
            "planning": "mistral:7b",
            "coding": "codellama:7b",
            "analysis": "mistral:7b",
        },
    ),
    "high_end_recommended": ModelProfile(
        key="high_end_recommended",
        tier="high_end",
        label="High-end recommended",
        description="16-32 GB RAM bundle with Mistral planning and Qwen 14B coding.",
        models={
            "intent": "phi3",
            "planning": "mistral:7b",
            "coding": "qwen2.5-coder:14b",
            "analysis": "mistral:7b",
        },
    ),
    "high_end_alternative": ModelProfile(
        key="high_end_alternative",
        tier="high_end",
        label="High-end alternative",
        description="16-32 GB RAM alternative bundle using Gemma intent, Mixtral planning, and CodeLlama 13B coding.",
        models={
            "intent": "gemma:2b",
            "planning": "mixtral:8x7b",
            "coding": "codellama:13b",
            "analysis": "mixtral:8x7b",
        },
    ),
    "very_high_end_recommended": ModelProfile(
        key="very_high_end_recommended",
        tier="very_high_end",
        label="Very high-end recommended",
        description="32 GB+ RAM bundle with Mixtral planning and Qwen 32B coding.",
        models={
            "intent": "phi3",
            "planning": "mixtral:8x7b",
            "coding": "qwen2.5-coder:32b",
            "analysis": "mixtral:8x7b",
        },
    ),
    "very_high_end_alternative": ModelProfile(
        key="very_high_end_alternative",
        tier="very_high_end",
        label="Very high-end alternative",
        description="32 GB+ RAM alternative bundle with DeepSeek planning and CodeLlama 34B coding.",
        models={
            "intent": "phi3",
            "planning": "deepseek-v2:16b",
            "coding": "codellama:34b",
            "analysis": "deepseek-v2:16b",
        },
    ),
}


PROFILE_KEYS_BY_TIER = {
    "low_end": ("low_end_recommended", "low_end_alternative"),
    "mid_range": ("mid_range_recommended", "mid_range_alternative"),
    "high_end": ("high_end_recommended", "high_end_alternative"),
    "very_high_end": ("very_high_end_recommended", "very_high_end_alternative"),
}


def ram_tier_for_gb(ram_gb: float) -> str:
    if ram_gb <= 8:
        return "low_end"
    if ram_gb <= 16:
        return "mid_range"
    if ram_gb <= 32:
        return "high_end"
    return "very_high_end"


def recommended_profile_key(ram_gb: float) -> str:
    return PROFILE_KEYS_BY_TIER[ram_tier_for_gb(ram_gb)][0]


def alternative_profile_key(ram_gb: float) -> str:
    return PROFILE_KEYS_BY_TIER[ram_tier_for_gb(ram_gb)][1]


def get_profile(profile_key: str) -> ModelProfile:
    try:
        return PROFILES[profile_key]
    except KeyError as exc:
        raise ValueError(f"unknown model profile: {profile_key}") from exc


def recommended_profile_for_ram(ram_gb: float) -> ModelProfile:
    return get_profile(recommended_profile_key(ram_gb))


def available_profiles_for_ram(ram_gb: float) -> list[ModelProfile]:
    return [get_profile(profile_key) for profile_key in PROFILE_KEYS_BY_TIER[ram_tier_for_gb(ram_gb)]]


def unique_models(models_by_role: dict[str, str]) -> list[str]:
    ordered: list[str] = []
    for role in ROLE_ORDER:
        model_name = models_by_role.get(role)
        if model_name and model_name not in ordered:
            ordered.append(model_name)
    for model_name in models_by_role.values():
        if model_name and model_name not in ordered:
            ordered.append(model_name)
    return ordered


def estimate_model_storage_kib(model_names: list[str]) -> int:
    return sum(MODEL_STORAGE_KIB.get(model_name, DEFAULT_MODEL_STORAGE_KIB) for model_name in model_names)

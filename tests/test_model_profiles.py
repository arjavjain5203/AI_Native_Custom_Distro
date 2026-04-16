from ai_core.core.model_profiles import (
    alternative_profile_key,
    available_profiles_for_ram,
    estimate_model_storage_kib,
    recommended_profile_for_ram,
)


def test_recommended_profile_selection_uses_expected_ram_thresholds() -> None:
    assert recommended_profile_for_ram(8.0).models["coding"] == "qwen2.5-coder:1.5b"
    assert recommended_profile_for_ram(8.01).models["coding"] == "qwen2.5-coder:7b"
    assert recommended_profile_for_ram(16.0).models["coding"] == "qwen2.5-coder:7b"
    assert recommended_profile_for_ram(16.01).models["coding"] == "qwen2.5-coder:14b"
    assert recommended_profile_for_ram(32.0).models["coding"] == "qwen2.5-coder:14b"
    assert recommended_profile_for_ram(32.01).models["coding"] == "qwen2.5-coder:32b"


def test_available_profiles_include_recommended_and_alternative_per_tier() -> None:
    profiles = available_profiles_for_ram(12.0)

    assert [profile.key for profile in profiles] == [
        "mid_range_recommended",
        "mid_range_alternative",
    ]
    assert alternative_profile_key(40.0) == "very_high_end_alternative"


def test_storage_estimation_counts_unique_models_only_when_deduplicated_upstream() -> None:
    total = estimate_model_storage_kib(["phi3:mini", "gemma:2b", "qwen2.5-coder:1.5b"])

    assert total > 0

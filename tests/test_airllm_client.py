import sys
from types import SimpleNamespace

import pytest

from ai_core.models.airllm_client import AirLLMClient, AirLLMError


class FakeModel:
    def __init__(self, model_name: str, output: object = "generated text") -> None:
        self.model_name = model_name
        self.output = output
        self.generate_calls = 0

    def generate(self, prompts: list[str], **kwargs: object) -> list[object]:
        self.generate_calls += 1
        return [self.output]


class FakeAutoModel:
    load_calls = 0
    last_model_name: str | None = None

    @classmethod
    def from_pretrained(cls, model_name: str) -> FakeModel:
        cls.load_calls += 1
        cls.last_model_name = model_name
        return FakeModel(model_name)


def test_airllm_client_generates_and_reuses_cached_model(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = SimpleNamespace(AutoModel=FakeAutoModel)
    monkeypatch.setitem(sys.modules, "airllm", fake_module)
    FakeAutoModel.load_calls = 0

    client = AirLLMClient()

    first = client.generate("hello", model="test-model")
    second = client.generate("hello again", model="test-model")

    assert first == "generated text"
    assert second == "generated text"
    assert FakeAutoModel.load_calls == 1
    assert FakeAutoModel.last_model_name == "test-model"


def test_airllm_client_normalizes_dict_output(monkeypatch: pytest.MonkeyPatch) -> None:
    class DictModel(FakeModel):
        def generate(self, prompts: list[str], **kwargs: object) -> list[object]:
            return [{"generated_text": "normalized"}]

    class DictAutoModel:
        @classmethod
        def from_pretrained(cls, model_name: str) -> DictModel:
            return DictModel(model_name)

    fake_module = SimpleNamespace(AutoModel=DictAutoModel)
    monkeypatch.setitem(sys.modules, "airllm", fake_module)

    client = AirLLMClient()

    assert client.generate("hello", model="dict-model") == "normalized"


def test_airllm_client_raises_clear_error_when_dependency_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "airllm", raising=False)

    client = AirLLMClient(module_name="airllm_missing")

    with pytest.raises(AirLLMError, match="airllm is not installed"):
        client.generate("hello", model="missing-model")


def test_airllm_client_wraps_model_load_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenAutoModel:
        @classmethod
        def from_pretrained(cls, model_name: str) -> FakeModel:
            raise RuntimeError("load exploded")

    fake_module = SimpleNamespace(AutoModel=BrokenAutoModel)
    monkeypatch.setitem(sys.modules, "airllm", fake_module)

    client = AirLLMClient()

    with pytest.raises(AirLLMError, match="failed to load model 'broken-model'"):
        client.generate("hello", model="broken-model")


def test_airllm_client_wraps_generation_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenModel(FakeModel):
        def generate(self, prompts: list[str], **kwargs: object) -> list[object]:
            raise RuntimeError("generation exploded")

    class BrokenAutoModel:
        @classmethod
        def from_pretrained(cls, model_name: str) -> BrokenModel:
            return BrokenModel(model_name)

    fake_module = SimpleNamespace(AutoModel=BrokenAutoModel)
    monkeypatch.setitem(sys.modules, "airllm", fake_module)

    client = AirLLMClient()

    with pytest.raises(AirLLMError, match="generation failed for model 'broken-model'"):
        client.generate("hello", model="broken-model")

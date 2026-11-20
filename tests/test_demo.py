import json
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from medspeech.api import create_app
from medspeech import demo
from medspeech.demo import example_case, imaging_from_report, run_models


def test_example_provenance_and_source_boundaries():
    result = example_case()
    assert result.execution.stt == "not_run"
    assert result.execution.structure == "example_annotation"
    assert result.case.stt_transcript is None
    assert result.execution.message == "예시 전사문 · 모델 미실행"
    assert set(result.case.model_dump()) == {"reference_transcript", "stt_transcript", "simulated_mri_report", "scenario_diagnosis"}
    assert {v.value for v in result.audio_findings.symptoms} == {"머리가 계속 아프고", "구토"}
    assert "germinoma" not in result.audio_findings.model_dump_json()
    assert "생식세포종" not in result.imaging_findings.model_dump_json()
    assert result.imaging_findings.obstruction_site.value == "중뇌수도관"
    assert {v.value for v in result.imaging_findings.enlarged_ventricles} == {"측뇌실", "제3뇌실"}
    for value in [result.imaging_findings.obstruction_site, *result.imaging_findings.enlarged_ventricles]:
        assert value.evidence in result.case.simulated_mri_report
        assert value.value in value.evidence


def test_hidden_report_removes_input_and_findings():
    with TestClient(create_app(mode="smoke")) as client:
        result = client.get("/demo/api/case?include_mri=false").json()
    assert result["case"]["simulated_mri_report"] is None
    assert result["imaging_findings"] is None
    assert result["imaging_status"] == "no_information"
    assert result["audio_findings"]["symptoms"]
    assert imaging_from_report(None) is None
    assert imaging_from_report("별도의 명시적 소견 없음.").obstruction_site is None


@pytest.mark.parametrize("url", ["/", "/demo/aqueduct", "/demo/assets/style.css", "/demo/assets/app.js"])
def test_demo_served_without_models(url):
    with TestClient(create_app(mode="smoke")) as client:
        assert client.get(url).status_code == 200


def test_smoke_never_masquerades_as_real_stt():
    def forbidden():
        raise AssertionError("must not load fixture as real STT")
    result = run_models(forbidden, "smoke")
    assert result.execution.stt == "unavailable"
    assert result.case.stt_transcript is None
    assert result.audio_findings is None


def test_missing_audio_is_model_not_run(tmp_path):
    result = run_models(lambda: None, "full", audio_path=tmp_path/"absent.wav")
    assert result.execution.stt == "unavailable"
    assert result.execution.structure == "not_run"
    assert result.case.stt_transcript is None


class TestSTTDouble:
    __test__ = False
    name = "unit-test-stt-double"
    def transcribe(self, audio):
        return "구토도 했어요."


class TestLLMDouble:
    __test__ = False
    name = "unit-test-llm-double"
    def __init__(self, raw):
        self.raw = raw
        self.inputs = []
    def extract(self, text, prompt):
        self.inputs.append((text, prompt))
        return self.raw


@pytest.fixture
def case_audio(tmp_path, monkeypatch):
    path = tmp_path/"fictional.wav"
    sf.write(path, np.zeros(1600), 16000)
    monkeypatch.setattr(demo, "AUDIO_PATH", path)
    return path


@pytest.mark.parametrize("raw", ["invalid JSON", '{"diagnosis":"germinoma"}'])
def test_schema_failure_keeps_actual_stt_and_never_succeeds(case_audio, raw):
    llm = TestLLMDouble(raw)
    with TestClient(create_app(TestSTTDouble(), llm, "full")) as client:
        result = client.post("/demo/api/run", json={"include_mri": False}).json()
    assert result["case"]["stt_transcript"] == "구토도 했어요."
    assert result["case"]["reference_transcript"] == "머리가 계속 아프고 구토도 했어요."
    assert result["execution"]["stt"] == "completed"
    assert result["execution"]["structure"] == "schema_error"
    assert result["audio_findings"] is None and result["imaging_findings"] is None
    assert llm.inputs == [("구토도 했어요.", "grounded")]


def test_grounding_failure(case_audio):
    llm = TestLLMDouble(json.dumps({"symptoms": [{"value": "없는 증상", "evidence": "없는 증상"}]}))
    result = run_models(lambda: (TestSTTDouble(), llm), "full")
    assert result.execution.structure == "grounding_error"
    assert result.audio_findings is None


def test_model_setup_failure_is_explicitly_not_run(case_audio):
    def unavailable():
        raise ImportError("models are not installed")
    result = run_models(unavailable, "full")
    assert result.execution.stt == "unavailable"
    assert "예시 전사문 · 모델 미실행" in result.execution.message
    assert result.case.stt_transcript is None
    assert result.audio_findings is None


def test_success_only_exposes_supported_symptoms(case_audio):
    llm = TestLLMDouble(json.dumps({"symptoms": [{"value": "구토", "evidence": "구토도 했어요."}]}))
    result = run_models(lambda: (TestSTTDouble(), llm), "full")
    assert result.execution.structure == "completed"
    assert set(result.audio_findings.model_dump()) == {"symptoms"}
    assert result.audio_findings.symptoms[0].value == "구토"
    assert llm.inputs == [("구토도 했어요.", "grounded")]


def test_stt_failure_does_not_write_reference_as_stt(case_audio):
    class BrokenSTT(TestSTTDouble):
        def transcribe(self, audio):
            raise RuntimeError("test failure")
    llm = TestLLMDouble("{}")
    result = run_models(lambda: (BrokenSTT(), llm), "full")
    assert result.execution.stt == "failed"
    assert result.case.stt_transcript is None
    assert not llm.inputs


def test_request_schema_errors_are_http_422():
    with TestClient(create_app(mode="smoke")) as client:
        assert client.post("/demo/api/run", json={"include_mri": "false"}).status_code == 422
        assert client.post("/demo/api/run", json={"diagnosis": "invented"}).status_code == 422

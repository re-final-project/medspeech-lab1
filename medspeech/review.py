"""Immutable initial transcript review; only corrected text is reanalysed."""
import argparse
import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Literal

from pydantic import Field
from .demo import ROOT, StrictModel, ImagingFindings, load_case, imaging_from_report
from .comparison import REFERENCE, SIMULATED, Side, expected_answer, get_comparison, structure_side


def canonical(text):
    return " ".join(text.strip().rstrip(".。 ").split())


def model_environment(mode):
    return mode == "full" and all(importlib.util.find_spec(name) is not None for name in ["torch", "transformers"])


class ReviewSession(StrictModel):
    reference_transcript: str
    initial: Side
    source: Literal["simulated", "actual_stt"]
    label: str
    analysis_mode: Literal["model", "example"]
    simulated_mri_report: str | None
    imaging_findings: ImagingFindings | None


class ReviewRequest(StrictModel):
    corrected_transcript: str = Field(min_length=1, max_length=2000)
    analysis_mode: Literal["model", "example"] = "model"
    include_mri: bool = True
    input_kind: Literal['initial', 'corrected', 'stt_lora', 'stt_turbo'] = 'corrected'


class ReviewAnalysis(StrictModel):
    status: Literal["completed", "example", "failed", "unavailable"]
    message: str
    side: Side
    llm_model: str | None = None
    stt_executed: bool = False
    simulated_mri_report: str | None
    imaging_findings: ImagingFindings | None
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    input_version: str | None = None
    provider: str | None = None
    schema_version: str | None = None
    schema_valid: bool | None = None
    error_code: str | None = None
    symptom_output: dict | None = None


def review_session(mode="full", source="auto", include_mri=True, backend="local"):
    available = (mode == 'full') if backend == 'hf' else model_environment(mode)
    example = source == "simulated" or not available
    value = get_comparison(include_mri, "simulated" if example else "auto", allow_stored=available)
    initial = value.transcript.model_copy(deep=True)
    # Only the prescribed simulation receives example results in this feature.
    if not example:
        initial.example_answer = None
    return ReviewSession(
        reference_transcript=REFERENCE, initial=initial,
        source="simulated" if example or value.source == "simulated" else "actual_stt",
        label="모의 전사문 · STT 미실행" if value.source == "simulated" else value.label,
        analysis_mode="example" if example else "model",
        simulated_mri_report=value.simulated_mri_report, imaging_findings=value.imaging_findings,
    )


def reanalyse(request, provider, mode, backend="local"):
    text = request.corrected_transcript
    report = load_case().simulated_mri_report if request.include_mri else None
    side = Side(text=text)  # No automatic expected_answer for arbitrary drafts.
    def result(status, message, llm_model=None):
        from .hf_models import input_version
        return ReviewAnalysis(status=status, message=message, side=side, llm_model=llm_model,
                              input_version=input_version(text, request.input_kind),
                              schema_version='consultation-v1' if backend == 'local' or request.analysis_mode == 'example' else 'two-symptoms-v1',
                              simulated_mri_report=report, imaging_findings=imaging_from_report(report))
    if not text.strip():
        side.structure_status = "empty_transcript"
        return result("failed", "재분석 실패 · 빈 수정문")
    if request.analysis_mode == "example":
        if canonical(text) not in {canonical(REFERENCE), canonical(SIMULATED)}:
            return result("unavailable", "모델 미실행 · 예시 결과는 지정된 긍정/부정 시연 문장에만 제공됩니다.")
        side.example_answer = expected_answer(text)
        return result("example", "모의 결과 · 예시 결과 · 구조화 모델 미실행")
    if backend == 'hf' and mode == 'full':
        from .hf_models import HFQwen, ModelError, SCHEMA_VERSION, input_version
        from .comparison import SymptomStates, Mention
        adapter = HFQwen()
        response = result('failed', '재분석 실패', adapter.name)
        response.input_version = input_version(text, request.input_kind)
        response.provider = adapter.provider
        response.schema_version = SCHEMA_VERSION
        messages = {'token_missing':'HF_TOKEN 누락 · 모델 미실행',
                    'provider_unsupported':'제공자 미지원 · 모델/JSON Schema 지원 조합을 확인하세요',
                    'provider_check_failed':'제공자 지원 확인 실패 · 다시 시도하세요',
                    'client_unavailable':'InferenceClient 준비 실패 · hf 의존성을 확인하세요',
                    'call_failed':'모델 호출 실패 · 다시 시도하세요',
                    'schema_error':'JSON 스키마 검증 실패', 'grounding_error':'원문 근거 검증 실패',
                    'content_error':'증상·부정 표현 내용 검증 실패'}
        try:
            values = adapter.analyse(text)
            response.symptom_output = values.model_dump()
            labels = {'present':'있음','absent':'없음','not_mentioned':'언급 없음'}
            side.model_states = SymptomStates(**{k:Mention(status=labels[v.mention_status], evidence=v.evidence_text)
                                                 for k,v in [(k,getattr(values,k)) for k in ['headache','vomiting']]})
            side.structure_status = 'completed'
            response.status = 'completed'
            response.schema_valid = True
            response.message = '수정문 재분석 완료 · 실제 HF 모델 결과'
        except ModelError as error:
            response.error_code = error.code
            response.message = '재분석 실패 · ' + messages.get(error.code,'모델 실행 실패')
            response.schema_valid = False if error.code == 'schema_error' else True if error.code in ['grounding_error','content_error'] else None
            side.structure_status = error.code if error.code in ['schema_error','grounding_error','content_error'] else 'failed'
            if error.code in ['token_missing','provider_unsupported','provider_check_failed','client_unavailable']:
                response.status = 'unavailable'
        return response
    if mode != "full":
        return result("unavailable", "모델 미실행 · 모의 검토 시연에서 예시 결과를 확인할 수 있습니다.")
    try:
        _, llm = provider()
    except Exception:
        return result("unavailable", "모델 미실행 · 구조화 모델을 준비하지 못했습니다. 모의 검토 시연을 이용하세요.")
    # Do not send the reference, initial transcript, MRI, or diagnosis to the LLM.
    structure_side(side, llm)
    if side.structure_status == "completed":
        return result("completed", "수정문 재분석 완료 · 실제 모델 결과", llm.name)
    return result("failed", f"재분석 실패 · {side.structure_status} · 수정문을 확인하고 재시도하세요.", llm.name)


def mount_review(app, provider, mode, backend='local'):
    @app.get("/demo/api/review", response_model=ReviewSession)
    def session(source: Literal["auto", "simulated"] = "auto", include_mri: bool = True):
        return review_session(mode, source, include_mri, backend)

    @app.post("/demo/api/review/reanalyse", response_model=ReviewAnalysis)
    def analyse(request: ReviewRequest):
        return reanalyse(request, provider, mode, backend)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--example", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT/"artifacts/review/reanalysis_run.json")
    args = parser.parse_args()
    from fastapi.testclient import TestClient
    from .api import create_app
    from .data import dump
    with TestClient(create_app(mode="full")) as client:
        initial = client.get("/demo/api/review", params={"source":"simulated" if args.example else "auto"}).json()
        response = client.post("/demo/api/review/reanalyse", json={
            "corrected_transcript": REFERENCE, "analysis_mode":"example" if args.example else "model"})
        response.raise_for_status()
        analysis = ReviewAnalysis.model_validate(response.json())
    dump(args.output, {"initial_snapshot":initial, "analysis":analysis.model_dump()})
    print(analysis.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

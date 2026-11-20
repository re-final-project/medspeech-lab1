"""One fictional case; separate scenario knowledge, speech, and report evidence."""
import argparse
import json
import time
import sys
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .schema import Consultation, Evidence, grounded

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = Path(__file__).with_name("cases") / "aqueduct_obstruction.json"
AUDIO_PATH = ROOT / "data/demo/aqueduct_patient.wav"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CaseData(StrictModel):
    reference_transcript: str
    stt_transcript: str | None
    simulated_mri_report: str | None
    scenario_diagnosis: str


class AudioFindings(StrictModel):
    symptoms: list[Evidence] = Field(default_factory=list)


class ImagingFindings(StrictModel):
    obstruction_site: Evidence | None = None
    enlarged_ventricles: list[Evidence] = Field(default_factory=list)


class ExecutionState(StrictModel):
    stt: Literal["not_run", "completed", "unavailable", "failed"] = "not_run"
    structure: Literal["example_annotation", "not_run", "completed", "schema_error", "grounding_error", "content_error", "failed"] = "example_annotation"
    message: str = "예시 전사문 · 모델 미실행"
    stt_model: str | None = None
    llm_model: str | None = None
    audio_seconds: float | None = None
    stt_seconds: float | None = None
    structure_seconds: float | None = None
    rtf: float | None = None


class DemoResponse(StrictModel):
    case: CaseData
    execution: ExecutionState
    audio_findings: AudioFindings | None
    imaging_findings: ImagingFindings | None
    imaging_status: Literal["report_text", "no_information"]
    imaging_method: str = "가상 판독문 문자열 근거 · 규칙 기반 · 영상 분석 미실행"
    audio_available: bool


class RunRequest(StrictModel):
    include_mri: bool = True


def load_case():
    case = CaseData.model_validate_json(CASE_PATH.read_text(encoding="utf-8"))
    # A stored reference is never promoted to an actual model transcription.
    case.stt_transcript = None
    return case


def imaging_from_report(report: str | None):
    """Literal matching for this supplied fictional report, never image analysis."""
    if report is None:
        return None
    result = ImagingFindings()
    sentences = [s.strip() + "." for s in report.split(".") if s.strip()]
    for sentence in sentences:
        if "중뇌수도관을 압박" in sentence:
            result.obstruction_site = Evidence(value="중뇌수도관", evidence=sentence)
        if "확장" in sentence:
            for name in ["측뇌실", "제3뇌실"]:
                if name in sentence:
                    result.enlarged_ventricles.append(Evidence(value=name, evidence=sentence))
    return result


def present(case, execution, audio_findings, include_mri):
    case = case.model_copy(deep=True)
    if not include_mri:
        case.simulated_mri_report = None
    return DemoResponse(
        case=case, execution=execution, audio_findings=audio_findings,
        imaging_findings=imaging_from_report(case.simulated_mri_report),
        imaging_status="report_text" if case.simulated_mri_report is not None else "no_information",
        imaging_method="가상 판독문 문자열 근거 · 규칙 기반 · 영상 분석 미실행",
        audio_available=AUDIO_PATH.is_file(),
    )


def example_case(include_mri=True):
    case = load_case()
    # Authored example annotations, explicitly not the output of an extractor/LLM.
    annotation = AudioFindings(symptoms=[
        Evidence(value="머리가 계속 아프고", evidence="머리가 계속 아프고"),
        Evidence(value="구토", evidence="구토도 했어요."),
    ])
    return present(case, ExecutionState(), annotation, include_mri)


def run_models(provider, mode, include_mri=True, audio_path=None):
    """Keep completed STT even if the existing LLM subsequently fails validation."""
    case = load_case()
    state = ExecutionState(structure="not_run")
    path = Path(audio_path) if audio_path is not None else AUDIO_PATH
    if mode != "full":
        state.stt = "unavailable"
        state.message = "예시 전사문 · 모델 미실행 — full 모드에서 실행하세요."
        return present(case, state, None, include_mri)
    if not path.is_file():
        state.stt = "unavailable"
        state.message = "예시 전사문 · 모델 미실행 — 합성 음성을 먼저 생성하세요."
        return present(case, state, None, include_mri)
    try:
        audio, sr = sf.read(path, dtype="float32")
        if sr != 16000 or audio.ndim != 1 or not 0 < len(audio) <= 30*sr or not np.isfinite(audio).all():
            raise ValueError("Expected finite mono 16 kHz audio, duration (0,30] seconds")
        try:
            stt, llm = provider()
        except Exception:
            state.stt = "unavailable"
            state.message = "예시 전사문 · 모델 미실행 — 모델 또는 실행 환경을 준비하지 못했습니다."
            return present(case, state, None, include_mri)
        state.stt_model, state.llm_model = stt.name, llm.name
        state.audio_seconds = len(audio)/sr
        start = time.perf_counter()
        text = stt.transcribe(audio)
        state.stt_seconds = time.perf_counter()-start
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty STT output")
        case.stt_transcript = text
        state.stt = "completed"
        state.rtf = state.stt_seconds / state.audio_seconds
    except Exception:
        state.stt = "failed"
        state.message = "STT 실행 실패 · 예시 정답은 실제 STT 출력으로 대체하지 않습니다."
        return present(case, state, None, include_mri)
    try:
        start = time.perf_counter()
        # The LLM receives ONLY the transcription. No MRI text or scenario label.
        raw = llm.extract(text, "grounded")
        state.structure_seconds = time.perf_counter()-start
        parsed = Consultation.model_validate_json(raw)
    except ValidationError:
        state.structure = "schema_error"
        state.message = "실제 STT 완료 · 구조화 실패 — JSON 스키마 오류"
        return present(case, state, None, include_mri)
    except Exception:
        state.structure = "failed"
        state.message = "실제 STT 완료 · 구조화 모델 실행 실패"
        return present(case, state, None, include_mri)
    if not grounded(parsed, text):
        state.structure = "grounding_error"
        state.message = "실제 STT 완료 · 구조화 실패 — 전사문 근거 불일치"
        return present(case, state, None, include_mri)
    # This bounded demo accepts only the stated symptom concepts. Unsupported
    # diagnoses or unrelated values are errors, never silently accepted/filtered.
    if any(not ("구토" in v.value or ("머리" in v.value and "아프" in v.value) or "두통" in v.value) for v in parsed.symptoms):
        state.structure = "content_error"
        state.message = "실제 STT 완료 · 구조화 실패 — 데모 범위 밖 증상 값"
        return present(case, state, None, include_mri)
    state.structure = "completed"
    state.message = "실제 STT·LLM 실행 완료 · 전사문 근거 검증 통과"
    return present(case, state, AudioFindings(symptoms=parsed.symptoms), include_mri)


def mount_demo(app: FastAPI, provider, mode):
    web = Path(__file__).with_name("web")
    app.mount("/demo/assets", StaticFiles(directory=web), name="demo-assets")

    @app.get("/", include_in_schema=False)
    @app.get("/demo/aqueduct", include_in_schema=False)
    def page():
        return FileResponse(web/"index.html", headers={"Cache-Control": "no-store"})

    @app.get("/demo/api/case", response_model=DemoResponse)
    def get_case(include_mri: bool = True):
        return example_case(include_mri)

    @app.get("/demo/audio", include_in_schema=False)
    def get_audio():
        from fastapi import HTTPException
        if not AUDIO_PATH.is_file():
            raise HTTPException(404, "Synthetic case audio has not been generated")
        return FileResponse(AUDIO_PATH, media_type="audio/wav")

    @app.post("/demo/api/run", response_model=DemoResponse)
    def run_case(request: RunRequest):
        # HTTP 200 acknowledges the state envelope; execution.structure records
        # schema_error etc. UI never interprets HTTP 200 as extraction success.
        return run_models(provider, mode, request.include_mri)


def generate_audio():
    from .adapters import MMSTTS, resolve
    from .data import dump
    from .verbalize import spoken_text
    config = json.loads((ROOT/"configs/full.json").read_text(encoding="utf-8"))
    revisions = resolve(config, ROOT/"artifacts/full/model_revisions.json")
    case = load_case()
    audio = MMSTTS(config, revisions)(case.reference_transcript)
    AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    sf.write(AUDIO_PATH, audio, 16000, subtype="PCM_16")
    dump(AUDIO_PATH.with_suffix(".metadata.json"), dict(
        kind="synthetic_tts_not_patient_audio", reference_transcript=case.reference_transcript,
        tts_input=spoken_text(case.reference_transcript), model=config["tts"], revision=revisions["tts"],
        seed=config["seed"], sample_rate=16000, duration_seconds=len(audio)/16000,
        license="CC-BY-NC-4.0; see reports/data_license.md", stt_executed=False,
    ))
    print(f"Synthetic speech saved: {AUDIO_PATH} ({len(audio)/16000:.3f}s)")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Fictional aqueduct case demo")
    parser.add_argument("command", choices=["serve", "generate-audio", "run"], nargs="?", default="serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-mri", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT/"artifacts/demo/model_run.json")
    args = parser.parse_args()
    if args.command == "generate-audio":
        generate_audio()
    elif args.command == "serve":
        import uvicorn
        uvicorn.run("medspeech.api:app", host=args.host, port=args.port, access_log=False)
    else:
        from fastapi.testclient import TestClient
        from .api import create_app
        from .data import dump
        with TestClient(create_app(mode="full")) as client:
            response = client.post("/demo/api/run", json={"include_mri": not args.no_mri})
            response.raise_for_status()
            result = DemoResponse.model_validate(response.json())
        dump(args.output, result.model_dump())
        print(result.execution.model_dump_json(indent=2))
        print(f"Recorded actual stage states: {args.output}")


if __name__ == "__main__":
    main()

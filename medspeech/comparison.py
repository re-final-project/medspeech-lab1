"""Transcript comparison for one fictional case; never infer imaging from speech."""
import argparse
from difflib import SequenceMatcher
import json
import importlib.util
from pathlib import Path
import re
import sys
from typing import Literal

import numpy as np
import soundfile as sf
from pydantic import Field, ValidationError

from .demo import ROOT, StrictModel, ImagingFindings, load_case, imaging_from_report
from .schema import Consultation, Evidence, grounded

REFERENCE = "머리가 계속 아프고 구토는 안 했어요."
SIMULATED = "머리가 계속 아프고 구토를 했어요."
AUDIO_PATH = ROOT / "data/demo/comparison_patient.wav"
RESULT_PATH = ROOT / "artifacts/comparison/model_run.json"


class Mention(StrictModel):
    status: Literal["있음", "없음", "언급 없음"]
    evidence: str | None = None


class SymptomStates(StrictModel):
    headache: Mention
    vomiting: Mention


class Side(StrictModel):
    text: str
    structure_status: Literal["not_run", "completed", "schema_error", "grounding_error", "content_error", "failed", "empty_transcript"] = "not_run"
    model_states: SymptomStates | None = None
    model_json: Consultation | None = None
    example_answer: SymptomStates | None = None


class Difference(StrictModel):
    kind: Literal["equal", "replace", "insert", "delete"]
    reference: str
    transcript: str


class Comparison(StrictModel):
    reference: Side
    transcript: Side
    source: Literal["simulated", "actual_stt", "edited"]
    stt_status: Literal["not_run", "completed", "unavailable", "failed"]
    stt_transcript: str | None = None
    label: str
    stored_result: bool = False
    stt_model: str | None = None
    llm_model: str | None = None
    differences: list[Difference]
    simulated_mri_report: str | None
    imaging_findings: ImagingFindings | None
    imaging_status: Literal["report_text", "no_information"]
    example_method: str = "예시 정답 · 이 가상 발화에 한정한 문자열 주석 · 모델 결과 아님"


class CompareRequest(StrictModel):
    transcript: str = Field(max_length=2000)
    include_mri: bool = True


class CompareRunRequest(StrictModel):
    include_mri: bool = True


def symptom_key(value):
    if "구토" in value:
        return "vomiting"
    if "두통" in value or ("머리" in value and "아프" in value):
        return "headache"
    return None


def states_from_json(parsed, text):
    """Reuse the existing schema and grounding contract, preserving negated fields."""
    if not grounded(parsed, text):
        raise ValueError("grounding_error")
    result = {k: Mention(status="언급 없음") for k in ["headache", "vomiting"]}
    for values, status in [(parsed.symptoms, "있음"), (parsed.denied_symptoms, "없음")]:
        for value in values:
            key = symptom_key(value.value)
            if key is None:
                raise ValueError("content_error")
            if result[key].status not in ["언급 없음", status]:
                raise ValueError("content_error")
            result[key] = Mention(status=status, evidence=value.evidence)
    return SymptomStates(**result)


def expected_answer(text):
    """Bounded demonstration annotation; not a trained extractor or medical parser."""
    if not text.strip():
        return None
    patterns = [
        r"머리(?:가|는)?\s*(?:계속\s*)?아프(?:고|다|요|지\s*않(?:아요|았어요|다))?|두통(?:이|은|는)?(?:\s*(?:없어요|있어요))?",
        r"구토(?:는|를|도|가)?\s*(?:(?:안\s*)?(?:했어요|했다|해요)|하지\s*않(?:았어요|아요)|없어요|있어요)?",
    ]
    parsed = Consultation()
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            phrase = match[0].strip()
            value = "구토" if "구토" in phrase else phrase
            item = Evidence(value=value, evidence=phrase)
            target = parsed.denied_symptoms if re.search(r"안\s|않|없", phrase) else parsed.symptoms
            target.append(item)
    return states_from_json(Consultation.model_validate(parsed.model_dump()), text)


def build_comparison(text=SIMULATED, source="simulated", include_mri=True, stt_status="not_run"):
    report = load_case().simulated_mri_report if include_mri else None
    diffs = [Difference(kind=tag, reference=REFERENCE[a:b], transcript=text[c:d])
             for tag, a, b, c, d in SequenceMatcher(None, REFERENCE, text, autojunk=False).get_opcodes()]
    return Comparison(
        reference=Side(text=REFERENCE, example_answer=expected_answer(REFERENCE)),
        transcript=Side(text=text, example_answer=expected_answer(text),
                        structure_status="not_run" if text.strip() else "empty_transcript"),
        source=source, stt_status=stt_status,
        stt_transcript=text if source == "actual_stt" else None,
        label={"simulated": "모의 전사 오류 · STT 미실행", "actual_stt": "실제 STT 전사 결과", "edited": "직접 수정한 전사문 · STT 미실행"}[source],
        differences=diffs, simulated_mri_report=report,
        imaging_findings=imaging_from_report(report), imaging_status="report_text" if report is not None else "no_information",
    )


def structure_side(side, llm):
    if not side.text.strip():
        side.structure_status = "empty_transcript"
        return
    try:
        # Neither the MRI report nor the scenario diagnosis is included.
        raw = llm.extract(side.text, "grounded")
        parsed = Consultation.model_validate_json(raw)
    except ValidationError:
        side.structure_status = "schema_error"
        return
    except Exception:
        side.structure_status = "failed"
        return
    try:
        states = states_from_json(parsed, side.text)
    except ValueError as error:
        side.structure_status = str(error)
        return
    side.model_json = parsed
    side.model_states = states
    side.structure_status = "completed"


def structure_comparison(value, llm):
    value.llm_model = llm.name
    structure_side(value.reference, llm)
    structure_side(value.transcript, llm)
    return value


def compare_edited(request, provider, mode):
    value = build_comparison(request.transcript, "edited", request.include_mri)
    if not request.transcript.strip():
        value.label = "빈 전사문 · STT 미실행"
        return value
    if mode != "full":
        value.label += " · 구조화 모델 미실행"
        return value
    try:
        _, llm = provider()
    except Exception:
        value.label += " · 구조화 모델 사용 불가"
        return value
    return structure_comparison(value, llm)


def run_comparison(provider, mode, include_mri=True):
    fallback = build_comparison(include_mri=include_mri, stt_status="unavailable")
    metadata_path = AUDIO_PATH.with_suffix(".metadata.json")
    if mode != "full" or not AUDIO_PATH.is_file() or not metadata_path.is_file():
        fallback.label += " — 비교용 합성 음성 또는 모델 환경 미준비"
        return fallback
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata["reference_transcript"] != REFERENCE:
            raise ValueError("comparison audio reference mismatch")
        audio, sr = sf.read(AUDIO_PATH, dtype="float32")
        if sr != 16000 or audio.ndim != 1 or not 0 < len(audio) <= 30*sr or not np.isfinite(audio).all():
            raise ValueError("invalid comparison audio")
        stt, llm = provider()
    except Exception:
        fallback.label += " — 비교용 음성/모델 준비 실패"
        return fallback
    try:
        text = stt.transcribe(audio)
        if not isinstance(text, str):
            raise TypeError("STT must return text")
    except Exception:
        fallback.stt_status = "failed"
        fallback.label += " — STT 실행 실패"
        return fallback
    value = build_comparison(text, "actual_stt", include_mri, "completed")
    value.stt_model = stt.name
    if not text.strip():
        value.label = "실제 STT 실행 · 빈 전사문"
        return value
    return structure_comparison(value, llm)


def get_comparison(include_mri=True, source="auto", allow_stored=True):
    if allow_stored and source == "auto" and RESULT_PATH.is_file():
        try:
            value = Comparison.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
            if value.source != "actual_stt" or value.stt_status != "completed" or value.reference.text != REFERENCE or value.stt_transcript != value.transcript.text:
                raise ValueError("not an actual comparison run")
            view = build_comparison(value.transcript.text, "actual_stt", include_mri, "completed")
            value.simulated_mri_report, value.imaging_findings, value.imaging_status = view.simulated_mri_report, view.imaging_findings, view.imaging_status
            value.stored_result = True
            value.label = "저장된 실제 STT 결과 · 현재 요청에서 모델 재실행 안 함"
            return value
        except (ValueError, KeyError):
            pass
    return build_comparison(include_mri=include_mri)


def mount_comparison(app, provider, mode):
    @app.get("/demo/api/compare", response_model=Comparison)
    def get(include_mri: bool = True, source: Literal["auto", "simulated"] = "auto"):
        available = mode == "full" and all(importlib.util.find_spec(name) is not None for name in ["torch", "transformers"])
        return get_comparison(include_mri, source, allow_stored=available)

    @app.post("/demo/api/compare", response_model=Comparison)
    def edit(request: CompareRequest):
        return compare_edited(request, provider, mode)

    @app.post("/demo/api/compare/run", response_model=Comparison)
    def run(request: CompareRunRequest):
        return run_comparison(provider, mode, request.include_mri)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Fictional speech negation comparison")
    parser.add_argument("command", choices=["generate-audio", "run"])
    args = parser.parse_args()
    if args.command == "generate-audio":
        from .adapters import MMSTTS, resolve
        from .data import dump
        config = json.loads((ROOT/"configs/full.json").read_text(encoding="utf-8"))
        revisions = resolve(config, ROOT/"artifacts/full/model_revisions.json")
        audio = MMSTTS(config, revisions)(REFERENCE)
        AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
        sf.write(AUDIO_PATH, audio, 16000, subtype="PCM_16")
        dump(AUDIO_PATH.with_suffix(".metadata.json"), dict(reference_transcript=REFERENCE, model=config["tts"], revision=revisions["tts"],
             kind="synthetic_tts_not_patient_audio", duration_seconds=len(audio)/16000, license="CC-BY-NC-4.0; see reports/data_license.md"))
        print(f"Generated comparison speech: {len(audio)/16000:.3f}s")
    else:
        from fastapi.testclient import TestClient
        from .api import create_app
        from .data import dump
        with TestClient(create_app(mode="full")) as client:
            result = client.post("/demo/api/compare/run", json={"include_mri": True})
            result.raise_for_status()
            value = Comparison.model_validate(result.json())
        dump(RESULT_PATH, value.model_dump())
        print(json.dumps(dict(label=value.label, stt_status=value.stt_status, stt_transcript=value.stt_transcript,
              reference_structure=value.reference.structure_status, transcript_structure=value.transcript.structure_status), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from .schema import Consultation
from .verbalize import spoken_text

VERSION = "synthetic-ko-v1"
SR = 16000
# Authored fictional utterances. Gold is authored independently of extraction code.
CASES = [
 ("resp", "기침 상담", "기침", "발열", "타이레놀", "500", "mg", "기침 상담 때문에 왔어요. 기침이 있고 발열은 없어요. 타이레놀 500 mg을 먹었어요."),
 ("cardio", "혈압 상담", "두통", "흉통", "암로디핀", "130", "mmHg", "혈압 상담 때문에 왔어요. 두통이 있고 흉통은 없어요. 암로디핀 복용 중이고 혈압은 130 mmHg예요."),
 ("diabetes", "혈당 상담", "갈증", "구토", "메트포르민", "126", "mg/dL", "혈당 상담 때문에 왔어요. 갈증이 있고 구토는 없어요. 메트포르민을 먹고 공복 혈당은 126 mg/dL예요."),
 ("gi", "복통 상담", "복통", "설사", "오메프라졸", "20", "mg", "복통 상담 때문에 왔어요. 복통이 있고 설사는 없어요. 오메프라졸 20 mg을 먹어요."),
 ("pulmonary", "호흡 상담", "호흡곤란", "객혈", "벤토린", "97", "%", "호흡 상담 때문에 왔어요. 호흡곤란이 있고 객혈은 없어요. 벤토린을 쓰고 SpO2는 97 %예요."),
 ("thyroid", "갑상선 상담", "피로", "두근거림", "씬지로이드", "50", "mcg", "갑상선 상담 때문에 왔어요. 피로가 있고 두근거림은 없어요. 씬지로이드 50 mcg을 먹어요."),
 ("neuro", "신경 상담", "어지럼", "마비", "아스피린", "100", "mg", "신경 상담 때문에 왔어요. 어지럼이 있고 마비는 없어요. MRI 예약했고 아스피린 100 mg을 먹어요."),
 ("allergy", "알레르기 상담", "가려움", "호흡곤란", "세티리진", "10", "mg", "알레르기 상담 때문에 왔어요. 가려움이 있고 호흡곤란은 없어요. 세티리진 10 mg을 먹어요."),
 ("renal", "신장 상담", "부종", "혈뇨", "라식스", "1.2", "mg/dL", "신장 상담 때문에 왔어요. 부종이 있고 혈뇨는 없어요. 라식스 복용 중이고 Cr은 1.2 mg/dL예요."),
 ("pain", "통증 상담", "허리통증", "저림", "이부프로펜", "200", "mg", "통증 상담 때문에 왔어요. 허리통증이 있고 저림은 없어요. CT 찍었고 이부프로펜 200 mg을 먹어요."),
 ("fever", "발열 상담", "오한", "기침", "아세트아미노펜", "38.2", "도", "발열 상담 때문에 왔어요. 오한이 있고 기침은 없어요. 아세트아미노펜 복용했고 체온은 38.2 도예요."),
 ("lipid", "검사 상담", "피로", "흉통", "로수바스타틴", "110", "mg/dL", "검사 상담 때문에 왔어요. 피로가 있고 흉통은 없어요. 로수바스타틴 복용하고 LDL은 110 mg/dL예요."),
]


def dump(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_manifest(root):
    return [json.loads(x) for x in (Path(root)/"manifest.jsonl").read_text(encoding="utf-8").splitlines()]


def build(root, synth=None):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42); rows = []
    for i, (scenario, purpose, symptom, denied, drug, number, unit, text) in enumerate(CASES):
        split = "train" if i < 8 else "validation" if i < 10 else "test"
        ev = lambda value: {"value": value, "evidence": value}
        gold = dict(purpose=ev(purpose), symptoms=[ev(symptom)],
                    denied_symptoms=[{"value":denied,"evidence":f"{denied}{'은' if f'{denied}은 없어요' in text else '는'} 없어요"}],
                    medications=[ev(drug)], measurements=[dict(value=number, unit=unit, evidence=f"{number} {unit}")])
        Consultation.model_validate(gold)
        # Smoke audio is explicitly a tone fixture, not synthesized speech.
        audio = synth(text) if synth else (0.1*np.sin(2*np.pi*(220+i*13)*np.arange(SR)/SR)).astype("float32")
        if synth: print(f"TTS {i+1}/{len(CASES)}: {scenario}, {len(audio)/SR:.2f}s",flush=True)
        for variant in ["clean", "noise20db", "speed1.1"]:
            out = audio.copy()
            if variant == "noise20db":
                out += rng.normal(0, max(np.sqrt(np.mean(out**2)), 1e-5)/10, len(out))
            if variant == "speed1.1":
                out = np.interp(np.arange(0, len(out), 1.1), np.arange(len(out)), out)
            sid = f"s{i:02d}-{variant}"
            path = f"audio/{variant}/{sid}.wav"; (root/path).parent.mkdir(parents=True, exist_ok=True)
            sf.write(root/path, out, SR, subtype="PCM_16")
            rows.append(dict(sample_id=sid, audio_path=path, transcript=text, key_terms=[symptom, denied, drug],
                             structured_gold=gold, scenario_id=scenario, source_id=f"s{i:02d}", speaker_id="mms-kor-single" if synth else "fixture-tone",
                             variant=variant, split=split, data_version=VERSION, review_status="automatic_pending_listening",
                             audio_kind="mms_tts" if synth else "tone_fixture", utterance_type="abbreviation" if i in [4,6,8,9,11] else "standard",
                             tts_input=spoken_text(text) if synth else None,
                             duration_s=len(out)/SR))
    (root/"manifest.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows)+"\n", encoding="utf-8")
    return rows


def qc(root, rows=None):
    root = Path(root); rows = rows if rows is not None else load_manifest(root)
    checks=[]; ids=set(); seen={}; groups={}; contents={}
    def add(sid, kind, criterion, passed):
        checks.append(dict(sample_id=sid, error_type=kind, criterion=criterion, verdict="PASS" if passed else "FAIL", action_status="none" if passed else "open"))
    for r in rows:
        sid=r["sample_id"]
        add(sid,"duplicate_id","sample_id unique",sid not in ids); ids.add(sid)
        add(sid,"empty_transcript","nonempty stripped transcript",bool(r["transcript"].strip()))
        try: Consultation.model_validate(r["structured_gold"]); valid=True
        except Exception: valid=False
        add(sid,"gold_schema","Pydantic strict schema",valid)
        for key in ["scenario_id","source_id","transcript"]:
            group=(key,r[key]); groups.setdefault(group,set()).add(r["split"])
        path=root/r["audio_path"]
        add(sid,"missing_file","audio exists",path.is_file())
        if not path.is_file(): continue
        try:
            x,sr=sf.read(path); valid=x.ndim==1 and len(x)>0 and np.isfinite(x).all()
            add(sid,"sample_rate","16000 Hz",sr==SR)
            add(sid,"corrupt_audio","mono finite nonempty audio",bool(valid))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            add(sid,"duplicate_audio","unique PCM file hash",digest not in seen); seen[digest]=sid
            contents.setdefault(digest,set()).add(r["split"])
        except Exception: add(sid,"corrupt_audio","readable WAV",False)
    for r in rows:
        add(r["sample_id"],"split_leakage","scenario/source/transcript do not cross splits",
            all(len(groups[(k,r[k])])==1 for k in ["scenario_id","source_id","transcript"]))
    add("ALL","audio_leakage","audio hashes do not cross splits",all(len(v)==1 for v in contents.values()))
    with (root/"qc.csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=["sample_id","error_type","criterion","verdict","action_status"]); writer.writeheader(); writer.writerows(checks)
    speakers={s:sorted({r["speaker_id"] for r in rows if r["split"]==s}) for s in ["train","validation","test"]}
    summary=dict(samples=len(rows), checks=len(checks), failures=sum(c["verdict"]=="FAIL" for c in checks), speakers=speakers,
                 speaker_overlap=sorted(set(speakers["train"]) & set(speakers["test"])), speaker_disjoint_evaluation=False)
    summary["splits"]={s:dict(samples=sum(r["split"]==s for r in rows),scenarios=len({r["scenario_id"] for r in rows if r["split"]==s}),
                               audio_seconds=sum(r.get("duration_s",0) for r in rows if r["split"]==s)) for s in speakers}
    dump(root/"qc_summary.json",summary)
    return summary

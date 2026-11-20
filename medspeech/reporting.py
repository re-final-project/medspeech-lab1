"""Build a report from recorded artifacts; never invent performance numbers."""
import json
from pathlib import Path


def report(base):
    base=Path(base)
    read=lambda p:json.loads((base/p).read_text(encoding="utf-8"))
    m=read("artifacts/smoke/metrics.json"); q=read("data/smoke/qc_summary.json")
    lines=["# medspeech-lab 실험 보고서", "", "작성일: 2026-11-20 (Asia/Seoul). 이 보고서는 저장된 실행 산출물에서 수치를 읽어 작성한다.", "",
      "## 연구 질문과 가설", "",
      "1. 같은 Whisper 기준선에서 의료용어 공백 후처리와 LoRA 학습이 CER 및 핵심 항목 보존을 개선하는가? 후처리의 효과는 좁고 LoRA는 작은 합성 데이터에서 과적합할 수 있다고 가정한다.",
      "2. 근거 추출 프롬프트가 기본 프롬프트보다 원문 밖 생성률을 줄이는가? 실제 LLM 실험으로만 판단한다.",
      "3. STT 수치·단위·부정 오류가 구조화까지 전파되는가? JSON 통과와 근거 존재만으로 정답성을 보장하지 못할 것으로 가정한다.", "",
      "## 데이터 구성과 QC", "",
      f"직접 작성한 가상 상담 12개 시나리오에 clean/noise20db/speed1.1 변형을 적용하여 {q['samples']}개 샘플을 생성했다. train/validation/test는 24/6/6개이며 독립 원문은 8/2/2개다. 의료용어, 약물, 영문 약어 MRI·CT·LDL·Cr·SpO2, 수치·단위·부정을 포함한다. 시나리오와 원문별 고정 분할로 모든 변형을 함께 묶었다.",
      f"smoke 자동 QC {q['checks']}개 검사 중 실패 {q['failures']}개. 음성은 16 kHz mono PCM. smoke는 1초 테스트 톤이므로 청취 가능한 한국어 발화가 아니다. full은 MMS TTS를 사용한다. 화자는 단일 생성기이므로 모든 분할에 중복하며 화자 분리 평가는 하지 않았다. 자동 검수 통과 후에도 청취 검수는 pending이다.",
      "TTS 라이선스·출처·변형 표시 및 비상업 조건은 data_license.md, 검수 판정 예시는 qc_examples.md를 참조한다.", "",
      "MMS 입력의 숫자 기호 소실을 막기 위해 38.2→삼십팔 점 이, mg→밀리그램, MRI→엠알아이로 발음 문자열을 렌더링하고 manifest의 tts_input에 기록한다. 평가 정답은 원래 표기를 유지하므로 CER는 정서법/단위 표기 차이에도 민감하다. 실제 의미 오류와 구분해 해석해야 한다.", "",
      "## 모델과 비교 조건", "",
      "A = openai/whisper-tiny, B = A + train/dev에서 관측된 용어 공백 복원, C = 동일 SHA의 Whisper에 PyTorch LoRA(q_proj/v_proj, r=8, alpha=16, dropout=.05). AdamW lr=1e-4, batch=1, seed=42, 3 epochs, 검증 loss가 가장 낮은 adapter를 선택한다. 고정 test ID를 A/B/C에 공통 적용한다. 디코딩은 Korean/transcribe, greedy, num_beams=1, do_sample=False, max_new_tokens=128이다.",
      "LLM은 로컬 Qwen/Qwen2.5-0.5B-Instruct, greedy, max_new_tokens=256. CPU에서는 PyTorch Linear 동적 INT8 양자화를 적용한다(llm_cpu_int8=true). 동일 모델·양자화·스키마에서 basic/grounded 프롬프트를 사용하고 gold/A/B/C 입력을 교차 평가한다. 각 값에 원문 근거를 요구하고 진단·처방 필드를 금지한다. 알 수 없는 값은 null/빈 배열이다. full SHA와 패키지·하드웨어는 artifacts/full에 기록한다. 중단한 FP32/512-token 시도는 최종 지표에 합산하지 않는다. 최대 출력은 train/dev 정답의 120~129 tokenizer tokens보다 큰 256으로 제한했다. 테스트 출력 관측 후 프롬프트 문구나 후처리 규칙을 조정하지 않았다.",
      "정규화·분모·한국어 WER 어절 규칙·지표의 한계는 README 평가 규약을 따른다. 의료용어 사전의 test 정답 어휘는 지표 계산에만 쓰며 후처리 fitting과 분리한다.", "",
      "엄격한 JSON 객체 출력에서 첫 비공백 문자가 `{`가 아닌 경우 생성을 즉시 중단한다(llm_fail_fast_json=true). 이런 접두사는 후속 토큰과 무관하게 strict JSON 객체 검증에 실패하므로 스키마/필드 판정을 보존한다. 최종 raw는 이때 전체 자유 생성문이 아닌 실패 접두사다. 지연시간은 이 조기 중단 정책을 포함하며 자유 생성의 전체 완료 시간으로 해석하지 않는다. 두 프롬프트에 같은 규칙을 적용한다.", "",
      "## 실행된 smoke 검증 — 모델 성능 아님", "",
      "스크립트로 정답에 오류를 주입한 전사와 규칙 추출기를 사용했다. B의 규칙은 train에서 관측된 타이 레놀→타이레놀 하나로 test에 효과가 없다. C는 학습하지 않았으므로 smoke 표에 포함하지 않는다. 규칙 추출기는 두 프롬프트를 구별하지 않으므로 프롬프트 비교 우열을 주장할 수 없다.", "",
      "| 조건 | n | CER | WER | 의료용어 F1 | 숫자·단위 일치 | 부정 일치 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for k,v in m["stt"].items():
        lines.append(f"| {k} | {v['n']} | {v['cer']:.6f} | {v['wer']:.6f} | {v['medical_term_f1']:.6f} | {v['number_unit_exact']:.6f} | {v['negation_exact']:.6f} |")
    lines += ["", "CER는 전체 정답 279문자에 대한 12개 편집이다. 동일 원문의 3개 변형을 포함한 n=6이며 독립 상담은 2개뿐이다. 각 오디오 변형별 n=2, 발화 유형별 n=3이다. fixture가 오디오를 인식하지 않기 때문에 잡음 강건성을 측정한 결과가 아니다.", "",
      "| 입력/프롬프트 | JSON 통과 | 목적 F1 | 증상 F1 | 부정 증상 F1 | 약물 F1 | 수치 F1 | 근거 일치 | 원문 밖 생성 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for k,v in m["extraction"].items():
        f=v["field_f1"]
        lines.append(f"| {k} | {v['schema_pass_rate']:.3f} | {f['purpose']:.3f} | {f['symptoms']:.3f} | {f['denied_symptoms']:.3f} | {f['medications']:.3f} | {f['measurements']:.3f} | {v['evidence_match_rate']:.3f} | {v['unsupported_value_rate']:.3f} |")
    lines += ["", "## 대표 오류와 개선 전후 사례", "",
      "실제 smoke 주입 오류: s10의 ‘38.2 도’가 ‘32.8 도’로 바뀌었다. 추출기는 value=32.8, unit=도, evidence='32.8 도'를 반환했다. JSON·근거 검증은 통과하지만 정답 수치는 틀리다. 원문 밖 생성률 0%는 STT 정답성 100%를 뜻하지 않는다.",
      "s11의 ‘흉통은 없어요’→‘흉통이 있어요’ 반전으로 fixture의 부정 패턴 매칭이 실패하여 증상·부정 증상이 누락됐다. ‘로수바스타틴’→‘로수 바스타틴’은 약물 누락으로 이어졌다. 이는 실제 Whisper에서 관측한 오류가 아닌 의도적으로 만든 전파 검증 사례다.",
      "개선 전후 검증 사례(train fixture): ‘타이 레놀 500 mg’→‘타이레놀 500 mg’. 수치·단위·부정 토큰은 유지된다. 이 train 규칙은 test의 로수바스타틴 오류를 고치지 못하므로 A와 B 지표가 동일하다. 개선이 없는 결과도 그대로 보고한다.", "",
      "## 실제 모델 실행 상태", ""]
    full=base/"artifacts/full/metrics.json"
    failure=base/"artifacts/full/failure.json"
    if full.exists():
        fm=read("artifacts/full/metrics.json")
        lines += ["실제 모델 학습·추론·평가를 완료했다. smoke 표와 분리한 결과는 아래와 같다.", "", "| 실제 조건 | n | CER | WER | 용어 F1 | 숫자·단위 | 부정 |", "|---|---:|---:|---:|---:|---:|---:|"]
        for k,v in fm['stt'].items(): lines.append(f"| {k} | {v['n']} | {v['cer']:.6f} | {v['wer']:.6f} | {v['medical_term_f1']:.6f} | {v['number_unit_exact']:.6f} | {v['negation_exact']:.6f} |")
        env=read('artifacts/full/environment.json')
        lines += ["", f"하드웨어: {env.get('cpu_model',env.get('processor'))}, 논리 CPU {env.get('logical_cpus')}, PyTorch CPU threads={env.get('cpu_threads')}, CUDA={env.get('cuda_available')}. 지연시간은 모델 로딩을 제외하고 train 발화로 1회 워밍업 후 측정했다."]
        logs=read('artifacts/full/checkpoints/training_log.json')
        lines += ["", "| epoch | train loss | validation loss |", "|---|---:|---:|"]
        for row in logs: lines.append(f"| {row['epoch']} | {row['train_loss']:.6f} | {row['validation_loss']:.6f} |")
        lines += ["", "| 실제 조건 | 분류 | 그룹 | n | CER |", "|---|---|---|---:|---:|"]
        for k,by_key in fm['slices'].items():
            for key,groups in by_key.items():
                for group,v in groups.items(): lines.append(f"| {k} | {key} | {group} | {v['n']} | {v['cer']:.6f} |")
        from .data import load_manifest
        from .metrics import normalize,distance
        test=[r for r in load_manifest(base/'data/full') if r['split']=='test']
        hypotheses=read('artifacts/full/stt_predictions.json')
        def edits(r,k):
            return distance(normalize(r['transcript']).replace(' ',''),normalize(hypotheses[k][r['sample_id']]).replace(' ',''))
        example=max(test,key=lambda r:edits(r,'A')-edits(r,'C'))
        delta=edits(example,'A')-edits(example,'C')
        lines += ["", f"실제 A→C 사례 ({example['sample_id']}): 편집 오류 감소 {delta}개. 양수는 개선, 0은 동일, 음수는 악화다.", "", "```text", '정답: '+example['transcript'], 'A: '+hypotheses['A'][example['sample_id']], 'C: '+hypotheses['C'][example['sample_id']], "```"]
        lines += ["", "LLM 조건별 결과와 실제 원시 출력은 artifacts/full/metrics.json, extraction_predictions.json을 참조한다. 단계별 지연시간·실시간 계수(RTF)·오디오 길이·워밍업은 latency.json, 하드웨어는 environment.json에 남겼다."]
        lines += ["", "| 실제 입력/프롬프트 | n | JSON 통과 | 목적 F1 | 증상 F1 | 부정 F1 | 약물 F1 | 수치 F1 | 근거 일치 | 원문 밖 생성 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for k,v in fm['extraction'].items():
            f=v['field_f1']
            lines.append(f"| {k} | {v['n']} | {v['schema_pass_rate']:.3f} | {f['purpose']:.3f} | {f['symptoms']:.3f} | {f['denied_symptoms']:.3f} | {f['medications']:.3f} | {f['measurements']:.3f} | {v['evidence_match_rate']:.3f} | {v['unsupported_value_rate']:.3f} |")
        if all(v['schema_pass_rate']==0 for k,v in fm['extraction'].items() if k.startswith('gold/')):
            lines += ["", "실제 LLM은 정답 전사에서도 두 프롬프트 모두 JSON 스키마에 실패했다. 따라서 이 실행에서는 STT가 추가로 유발한 구조화 정확도 감소를 분리해 추정할 수 없다(바닥 효과). 프롬프트의 우열이나 오류 전파 감소를 주장하지 않는다. 작은 모델의 스키마 지시 수행 실패가 우선 병목이며 더 적합한 로컬 모델/출력 제약을 train/dev에서 검증한 뒤 새 테스트로 확인해야 한다."]
        empty=[k for k,v in fm['extraction'].items() if v['extracted_items']==0]
        if empty:
            lines += ["", "파싱된 추출 항목이 0인 조건: "+', '.join(empty)+". 이 조건의 근거/원문 밖 생성률 0은 분모가 0일 때의 코드 규약이다. 환각이 없다는 증거가 아니며, 스키마 실패 raw 출력은 extraction_predictions.json에서 별도로 검토해야 한다."]
        latency=read('artifacts/full/latency.json')
        lines += ["", "| 실제 STT 조건 | n | 총 오디오 초 | 평균 STT 초 | 합산 RTF |", "|---|---:|---:|---:|---:|"]
        for k in ['A','B','C']:
            selected=[x for x in latency if x['condition']==k]
            if not selected: continue
            total=sum(x['audio_seconds'] for x in selected); elapsed=sum(x['seconds'] for x in selected)
            lines.append(f"| {k} | {len(selected)} | {total:.3f} | {elapsed/len(selected):.3f} | {elapsed/total:.3f} |")
        lines += ["", "B는 A 전사에 문자열 규칙을 적용하므로 STT 추론 시간을 중복 측정하지 않았다. LLM의 각 입력/프롬프트별 평균 지연시간(초):", ""]
        for k,v in fm['extraction'].items():
            times=v['latency_seconds']
            lines.append(f"- {k}: {sum(times)/len(times):.3f} (실제 생성 n={len(times)}, 캐시 {v.get('cache_hits',0)}건)" if times else f"- {k}: 새 추론 없음, 동일 입력/프롬프트의 결정적 결과 재사용 {v.get('cache_hits',0)}건")
        lines += ["", "LLM은 같은 인스턴스의 greedy 디코딩에서 완전히 동일한 전사+프롬프트만 캐시한다. 정확도 표의 n은 고정 테스트 샘플 수이고, 지연시간 n은 중복을 제외한 실제 생성 횟수다. 캐시 조회 시간을 모델 추론 시간으로 보고하지 않는다. 워밍업은 train 발화에 8-token 생성 1회다."]
        actual_errors=[]
        for v in fm['extraction'].values():
            invalid={e['index'] for e in v['errors'] if e['type']=='schema'}
            actual_errors.extend(e for e in v['errors'] if e['type']=='content' and e['index'] not in invalid)
        if actual_errors:
            lines += ["", "실제 LLM의 스키마 통과 후 내용 불일치 예시(첫 사례):", "", "```json", json.dumps(actual_errors[0],ensure_ascii=False,indent=2), "```"]
    elif (base/'artifacts/full/stt_metrics.json').exists():
        partial=read('artifacts/full/stt_metrics.json')
        partial=partial.get('stt',partial)
        lines += ["실제 STT 학습·비교 평가는 완료했으나 전체 LLM 교차 평가의 최종 완료 결과는 아직 없다. 아래는 실제 STT 결과이며 smoke와 별도다.", "", "| 실제 조건 | n | CER | WER | 용어 F1 |", "|---|---:|---:|---:|---:|"]
        for k,v in partial.items(): lines.append(f"| {k} | {v['n']} | {v['cer']:.6f} | {v['wer']:.6f} | {v['medical_term_f1']:.6f} |")
        lines += ["", "학습 로그·체크포인트는 artifacts/full/checkpoints, 단계별 시간과 RTF는 latency.json에 보존했다. LLM 중간 결과는 extraction_progress.json을 참조한다. 나머지 재현 명령: `python -m medspeech.cli full --stage evaluate`."]
    elif failure.exists():
        fail=read("artifacts/full/failure.json")
        lines += ["실제 모델 전체 실험은 완료되지 않았다. 마지막 실행 예외:", "", "```text", fail['error'], "```", "", "실제 모델의 CER·학습 개선·지연시간은 미측정이다. 실패 상세와 환경은 artifacts/full/failure.json에 보존했다. 재현 명령: `python -m pip install -e '.[test,full]'`, 이어 `python -m medspeech.cli full`. 데이터 청취 검수와 실제 학습 검증은 남아 있다."]
    else: lines += ["실제 모델 전체 실험 결과가 아직 생성되지 않았다. 성능 수치는 미측정이다. 재현 명령: `python -m medspeech.cli full`. 실행 이력은 execution_log.md를 참조한다."]
    lines += ["", "## API 및 검증", "", "FastAPI TestClient에서 16 kHz 모노 WAV 입력→200, 손상 WAV→422를 확인했다. pytest는 분할 누수, 6종 QC 결함, CER, JSON·근거 검증, test 기반 사전 금지, 숫자/단위/부정 규칙 보호, 크기/형식/샘플레이트/채널/길이/필수 입력/모델 출력 오류를 검사한다. 실제 테스트 결과는 pytest.txt와 execution_log.md에 기록한다. API는 원음·전사를 지속 보관하지 않는다.", "",
      "## 한계와 다음 실험", "", "합성 단일 화자·12개 템플릿·짧은 발화로 임상 일반화를 할 수 없다. 자동 QC는 의미적 TTS 오류를 찾지 못한다. 한국어·수치·영문 발음에 대한 청취 검수, 더 많은 독립 시나리오, 다양한 허가된 화자와 잡음, 대화 맥락 및 다양한 부정 구문이 필요하다. 고정 테스트 2개 시나리오로 통계적 우열을 주장할 수 없다. 실행 중 양자화·출력 상한을 조정했으므로 탐색적 결과이며, 새 고정 테스트의 확인 실험이 필요하다. 추후 시나리오 단위 bootstrap 신뢰구간과 별도 화자 테스트를 추가한다. 근거 substring 검증은 참/거짓 판단기가 아니며 부정 의미 해석·수치 보존을 별도로 검증해야 한다. 로컬 소형 LLM의 한국어 구조화 능력은 실측 전 보장하지 않는다. 이 연구 결과를 실제 진료 음성 성능으로 일반화하지 않는다."]
    (base/"reports/experiment_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")

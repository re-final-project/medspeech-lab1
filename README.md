# medspeech-lab

한국어 가상 의료 상담의 STT 전사 품질과 구조화 오류 전파를 연구하는 실행 가능한 포트폴리오입니다. 진단·처방을 생성하지 않으며 실제 환자 데이터는 없습니다. 합성 음성 실험을 실제 진료 성능으로 일반화하지 않습니다.

두 경로를 분리합니다. `smoke`는 CPU에서 테스트 톤·스크립트 오류 전사·규칙 추출기로 데이터 QC, 지표, JSON, API를 확인합니다. 이 규칙 추출기는 LLM이 아니며 기본/근거 프롬프트를 구별하지 않습니다. `full`은 MMS Korean TTS, Whisper tiny, 같은 Whisper 체크포인트의 PyTorch LoRA, 로컬 Qwen LLM을 사용합니다. 실제 실행 상태와 수치는 [실험 보고서](reports/experiment_report.md)에 기록합니다.

실제 실행 결과: pytest 21개와 smoke 통과, 실제 합성 음성 36개 QC 실패 0, CPU LoRA 3 epochs 완료. 고정 테스트 6개에서 실제 CER는 A 36.56%, B 36.56%, C 31.90%였습니다. 로컬 Qwen의 JSON 통과율은 8개 조건 모두 0%여서 구조화 품질은 해결되지 않았습니다. API는 이런 모델 출력을 502로 거부하도록 구현되어 있습니다. 이 한계와 실패 원문을 보고서에 포함했으며, smoke 대역 모델의 성공을 실제 LLM 성능으로 제시하지 않습니다.

## 설치 (Windows PowerShell)

Python 3.11 또는 3.12, 디스크 여유 약 8 GB 이상을 권장합니다. CUDA는 필수가 아니지만 실제 학습과 LLM 추론은 CPU에서 느릴 수 있습니다. 아래 명령은 프로젝트 폴더에서 실행합니다. 활성화 스크립트를 사용하지 않아 실행 정책 변경이 필요 없습니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m medspeech.cli smoke
```

## 뇌실 통로 폐쇄 가상 사례 데모

기존 FastAPI 앱에 로컬 단일 페이지를 추가했습니다. 서버를 시작한 다음 브라우저에서 [가상 사례 화면](http://127.0.0.1:8765/demo/aqueduct)을 여세요.

```powershell
.\.venv\Scripts\python.exe -m medspeech.demo serve --port 8765
```

기본 화면은 **수도관 폐쇄**와 **예시 전사문 · 모델 미실행** 상태입니다. 별도 모델 설치 없이 페이지와 예시 주석, 가상 판독문 근거를 확인할 수 있습니다. 정상 흐름 버튼은 측뇌실 → 제3뇌실 → 중뇌수도관 → 제4뇌실을 연결하며, 수도관 폐쇄 버튼은 압박 지점에서 화살표를 멈추고 상류 확장을 표시합니다. 개념도 상태와 입력의 추출 결과는 독립적입니다. 정상 흐름을 선택해도 가상 판독문 자체를 정상으로 바꾸지 않습니다.

**가상 MRI 판독문 숨기기**를 누르면 판독문 텍스트, 폐쇄 관련 위치, 확장된 뇌실 및 그 근거를 제거하고 ‘영상 정보 없음’을 표시합니다. 개념도와 시나리오 설정은 입력 소견과 구분되어 남습니다. ‘현재 사례 JSON 저장’도 숨김 상태를 반영합니다.

`medspeech/cases/aqueduct_obstruction.json`은 `reference_transcript`, `stt_transcript`, `simulated_mri_report`, `scenario_diagnosis`를 구분합니다. 기준 사례의 `stt_transcript`는 null이고, 실제 STT 호출이 완료된 경우에만 응답/실험 파일에 실제 문자열을 기록합니다. 원인 질환명은 시나리오 설정에만 있으며 STT·LLM의 입력에 전달하지 않습니다. 음성 결과는 증상만 노출하고, 영상 소견은 **가상 판독문 문자열 근거 · 규칙 기반**으로 표시합니다. MRI 이미지, 질환 후보 순위·확률, 치료 추천은 사용하지 않습니다.

실제 모델 연결은 기존 `WhisperAdapter`와 `LocalLLM`을 공유합니다. `[full]` 의존성을 설치하고 기존 SHA lock을 유지하세요. 배포물에는 이 한 발화의 TTS 합성 WAV와 출처 metadata가 포함됩니다. 다시 생성하거나 CLI에서 실제 실행 결과를 기록하려면:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test,full]'
.\.venv\Scripts\python.exe -m medspeech.demo generate-audio
.\.venv\Scripts\python.exe -m medspeech.demo run
# 판독문을 제공하지 않는 상태의 실제 실행 기록:
.\.venv\Scripts\python.exe -m medspeech.demo run --no-mri --output artifacts/demo/no_mri_run.json
```

UI의 ‘합성 음성으로 STT·LLM 실행’도 같은 경로를 호출합니다. `MEDSPEECH_MODE=smoke`인 서버는 대역 모델을 실제 STT로 표시하지 않고 모델 미실행 상태를 반환합니다. 모델 환경이 없거나 실행에 실패해도 예시 정답을 실제 출력으로 채우지 않습니다. LLM 스키마 오류 시 실제 STT는 유지하고 음성 구조화는 null로 반환합니다. `/demo/api/run`의 HTTP 200은 실행 상태 envelope 수신을 뜻하며, 구조화 성공은 반드시 `execution.structure == "completed"`로 판단합니다. 웹 요청은 사례 원음이나 전사를 파일로 저장하지 않고, `demo run` CLI만 가상 사례의 실험 기록을 저장합니다.

기본 데모의 초기 검증은 [실행·검증 보고서](reports/demo_report.md)에 정리했습니다. 당시 브라우저 검증은 정책 차단으로 미완료였으며, 2026-11-22 전사 비교 확장에서는 실제 브라우저 연결·클릭 검증도 완료했습니다([비교 기능 보고서](reports/comparison_report.md)). 선택적인 DOM 테스트는 Node.js와 개발 의존성이 필요합니다.

```powershell
npm install
npm run test:ui
.\.venv\Scripts\python.exe -m pytest -q
```

관리형 Windows의 Hugging Face symlink 검사 문제가 있으면 기존 복사 캐시 도구와 같은 `tools/run_demo_windows_copy_cache.py`를 사용하세요.

```powershell
.\.venv\Scripts\python.exe tools\run_demo_windows_copy_cache.py generate-audio
.\.venv\Scripts\python.exe tools\run_demo_windows_copy_cache.py run
```

### 전사 오류 비교

같은 페이지의 **전사 오류 비교** 영역에서 원본과 전사를 비교합니다. 넓은 화면에서는 두 열, 좁은 화면에서는 읽기 쉬운 세로 배열입니다. 서로 다른 문자 구간을 강조하고 두통·구토의 「있음 / 없음 / 언급 없음」과 근거 문구를 표시합니다. 비교용 원본은 `머리가 계속 아프고 구토는 안 했어요.`이며, 기존 긍정 발화·합성 음성을 덮어쓰지 않습니다.

- full 모델 의존성과 저장된 실제 실행 결과가 있으면 그 전사를 표시하고 **저장된 결과 · 현재 요청에서 재실행 안 함**을 알립니다. 실제 STT 실행 버튼으로 다시 실행할 수 있습니다.
- 모델 환경/실행 결과가 없으면 `머리가 계속 아프고 구토를 했어요.`를 **모의 전사 오류 · STT 미실행**으로 표시합니다. ‘모의 전사 오류 보기’ 버튼으로 언제든 이 예시를 선택할 수 있습니다. 이때 `stt_transcript`는 null입니다.
- 실제 구조화에는 기존 `LocalLLM`, `Consultation`, `grounded()`를 재사용합니다. 실패한 모델 결과는 null로 두고, 별도 **예시 정답 · 한정 문자열 주석 · 모델 결과 아님**으로 시연용 상태를 표시합니다. 예시에서는 두통 양쪽 있음, 구토 원본 없음/모의 전사 있음입니다.
- 직접 수정한 전사는 실제 STT로 표시하지 않습니다. 빈 전사는 ‘언급 없음’으로 채우지 않고 **빈 전사문 · 평가 불가**로 처리합니다. 규칙 주석은 이 가상 발화의 한정된 표현만 다루며, 일반 한국어 부정 해석이나 맞춤법 복원 모델이 아닙니다.
- 전사문 편집과 MRI 소견은 독립적입니다. 판독문을 끄면 기존 소견과 비교 JSON 모두 ‘영상 정보 없음’/null이고, **가상 시나리오 · 교육용 개념도**는 남습니다. 증상에서 폐쇄·종양 종류를 추정하지 않습니다.

```powershell
# full 설치 및 모델 SHA 설정은 위 절차와 동일합니다.
.\.venv\Scripts\python.exe -m medspeech.comparison generate-audio
.\.venv\Scripts\python.exe -m medspeech.comparison run
.\.venv\Scripts\python.exe -m medspeech.demo serve --port 8765
# 선택적 Windows 복사 캐시 경로:
.\.venv\Scripts\python.exe tools\run_comparison_windows_copy_cache.py run
```

비교용 합성 음성은 `data/demo/comparison_patient.wav`, 실제 결과는 `artifacts/comparison/model_run.json`에 기록합니다. 웹 요청은 새 결과를 파일로 보관하지 않습니다. CLI만 가상 사례의 실험 기록을 저장합니다. [전체 검증·실제 모델 실행 범위](reports/comparison_report.md)와 [화면 예시](reports/comparison-preview.jpg)를 확인하세요.

실제 모델 설치와 데이터 생성·QC·학습·평가 순서:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test,full]'
$env:HF_HOME = Join-Path (Get-Location) '.cache\huggingface'
.\.venv\Scripts\python.exe -m medspeech.cli full --stage generate
.\.venv\Scripts\python.exe -m medspeech.cli qc --data .\data\full
.\.venv\Scripts\python.exe -m medspeech.cli full --stage train
.\.venv\Scripts\python.exe -m medspeech.cli full --stage evaluate
# STT 예측·체크포인트가 있고 LLM 평가만 다시 실행할 때:
.\.venv\Scripts\python.exe -m medspeech.cli full --stage structure
# 위 세 단계를 한 번에 실행하려면:
.\.venv\Scripts\python.exe -m medspeech.cli full
```

최초 모델 버전은 Hugging Face에서 commit SHA를 조회해 `artifacts/full/model_revisions.json`에 고정합니다. 재현 시 이 파일을 보존하세요. 실행 설정은 `configs/full.json`, 환경은 `artifacts/*/environment.json`에 저장됩니다. full 실패 시 `artifacts/full/failure.json`에 실제 예외가 남습니다. 설정 변경 시 기존 결과를 다른 폴더로 보존하고 `--base`로 복사한 프로젝트를 지정하세요. 기본 데이터 생성은 같은 데이터 버전 경로를 덮어쓰므로 검수 수정 데이터는 별도 버전으로 관리하세요.

관리형 Windows에서 Hugging Face의 symlink 임시 디렉터리 검사에 PermissionError가 발생하면 `python tools\run_windows_copy_cache.py full`로 동일 실험을 파일 복사 캐시 방식으로 실행할 수 있습니다. 이 스크립트는 모델·평가 코드를 바꾸지 않습니다. 실제 호스트의 설치 우회 및 명령 기록은 `reports/execution_log.md`를 참조하세요.

## API

```powershell
$env:MEDSPEECH_MODE = 'smoke'
.\.venv\Scripts\python.exe -m uvicorn medspeech.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

다른 PowerShell에서:

```powershell
curl.exe -X POST 'http://127.0.0.1:8000/infer' -F 'file=@data/smoke/audio/clean/s00-clean.wav;type=audio/wav'
```

실제 로컬 모델은 full 데이터 생성으로 SHA lock 파일을 만든 뒤 `$env:MEDSPEECH_MODE = 'full'`로 서버를 시작합니다. 기본 mode도 full입니다. `/infer`는 WAV MIME과 실제 헤더, 10 MiB, 모노 16 kHz, 길이 0초 초과 30초 이하, 유한 샘플을 검사합니다. 잘못된 입력은 413/415/422, 준비되지 않은 full 모델은 503, 스키마·근거 불합격은 502입니다. 응답에는 모델 이름, 모드, 전사, Pydantic 구조화 결과, 단계별 시간과 RTF가 포함됩니다. `/docs`에서 스키마를 확인할 수 있습니다.

서버는 원음·전사를 애플리케이션 파일이나 로그에 저장하지 않습니다. 업로드는 Starlette의 요청 임시 저장소를 거칠 수 있으며 요청 종료 시 닫힙니다. 요청 크기 상한은 파싱 후 파일 읽기에도 적용됩니다. 인터넷 공개 배포에는 프록시의 전체 요청 크기 제한·인증·동시성 제어가 추가로 필요합니다. 실험 배치 경로는 가상 데이터와 예측을 의도적으로 저장합니다. API 정책과 구분합니다.

## 데이터와 평가 규약

12개 시나리오/원문 × 3개 변형 = 36개 샘플. 시나리오 8/2/2개를 train/validation/test로 고정하여 각각 24/6/6개입니다. 동일 원문·시나리오와 모든 변형은 한 분할에만 있습니다. clean, 백색잡음 20 dB SNR, 1.1배 리샘플링(피치도 변화)을 구분합니다. 음성 경로·정답·핵심 용어·구조화 정답·화자·변형·버전·검수 상태는 JSONL manifest에 기록합니다. TTS 단일 화자 중복을 보고하며 화자 분리 성능을 주장하지 않습니다. 자동 QC 후 청취 검수는 미완료 상태로 남습니다.

MMS의 숫자 토큰 소실을 피하기 위해 `verbalize.py`에서 수치(38.2→삼십팔 점 이), 단위(mg→밀리그램), 약어(MRI→엠알아이)를 발음 문자열로 바꿉니다. 그 결과를 `tts_input`에 남기며 원래 전사 정답은 보존합니다. CER는 숫자 표기와 한국어 읽기의 차이도 오류로 세므로 정서법 차이에 민감합니다. 이를 임상적 수치 오류와 동일시하지 마세요. 발음 렌더러는 0~9999 및 소수만 지원하며 범위를 벗어나면 실패합니다.

* CER: NFKC, 소문자화, 문장부호 제거(소수점·슬래시·% 유지), 연속 공백 정리 후 공백을 제거한 문자 단위 micro edit distance / 정답 문자 수.
* WER: 동일 정규화 후 공백 기준 어절 토큰. 형태소 분석 WER가 아닙니다. 숫자를 한국어 읽기로 바꾸거나 부정을 삭제하지 않습니다.
* 의료용어 F1: 평가 정답 key_terms의 어휘 집합에 대해 전사 내 문자열 존재를 세는 micro F1. 복합어 부분 일치와 어휘 밖 환각을 포괄하지 못합니다.
* 숫자·단위 일치율: 추출한 숫자/단위 문자열 multiset의 샘플별 정확 일치. 임상 수치 의미 동치나 단위 변환은 적용하지 않습니다.
* 부정 일치율: 정답의 명시적 부정 근거 구문이 모두 보존된 샘플 비율. 새로운 부정의 추가 여부까지 포괄하는 의미 판별기는 아닙니다.
* LLM: 동일 모델/스키마, basic/grounded × gold/A/B/C 전사. strict JSON 통과율, 필드별 `(value, unit)` micro F1, 원문 근거 포함·값 포함 비율, 원문에 없는 값/단위 생성률을 별도로 계산합니다. 스키마 실패는 빈 예측으로 채점하며 오류 원문을 보존합니다. 근거/원문 밖 생성률의 분모는 스키마를 통과해 파싱된 추출 항목 수이며, 스키마 실패 출력의 환각을 포함하지 않습니다. 근거 일치는 인과적 정당성/정확한 부정 해석을 보증하지 않습니다. 분모가 0인 항목 비율은 0입니다.

test의 조건별 ID는 metrics.json에 저장됩니다. 잡음·발화 유형별 `n`을 함께 보고합니다. 테스트를 후처리 fitting에 전달하면 예외가 발생합니다. 사전은 train/dev 가설에서 실제 관측된 용어 내부 공백만 고치므로 테스트에서 개선이 없을 수 있습니다.

기본 로컬 LLM은 CPU에서 PyTorch Linear 동적 INT8 양자화를 적용합니다(`llm_cpu_int8=true`). GPU에서는 원래 가중치를 사용합니다. 모델 ID/SHA와 양자화 여부를 함께 기록하며, 프롬프트 비교는 같은 실행의 같은 LLM 설정 안에서 수행합니다. FP32와 INT8의 정확도·속도를 동일 조건으로 간주하지 않습니다.

LLM은 최대 256 tokens를 생성합니다(train/dev 정답은 동일 tokenizer에서 120~129 tokens). 중복 입력+동일 프롬프트는 같은 greedy 모델의 출력을 재사용합니다. 정확도는 모든 고정 테스트 샘플에 계산하고, 지연시간 배열에는 새로 생성한 호출만 기록합니다. `generation_calls`, `cache_hits`와 예측별 `cache_hit`으로 분모를 확인할 수 있습니다. B가 A와 같은 전사이면 별도의 LLM 지연시간을 주장하지 않습니다.

`llm_fail_fast_json=true`는 첫 비공백 문자가 `{`가 아니면 생성을 중단합니다. 엄격한 JSON 객체 파서는 이런 접두사 뒤에 무엇을 생성해도 통과하지 못하므로 유효 JSON을 거부하지 않는 검사입니다. 결과를 고치거나 진짜 JSON처럼 감싸지 않습니다. 저장 raw는 이 경우 전체 완성문이 아닌 실패 접두사이며, 지연시간도 실패 조기 중단을 포함한 실제 파이프라인 시간입니다. 전체 자유 생성 시간과 구분하세요.

## 코드와 산출물

| 경로 | 역할 |
|---|---|
| `medspeech/data.py` | 가상 정답, TTS/테스트 톤, 변형, 분할, QC CSV |
| `medspeech/schema.py` | 값·근거·수치 단위의 엄격한 JSON 스키마 |
| `medspeech/adapters.py` | 실제/대역 STT·LLM·TTS, prompt, SHA 고정, 후처리 |
| `medspeech/training.py` | PyTorch AdamW LoRA, 검증 loss 기반 best, 체크포인트/로그 |
| `medspeech/metrics.py` | 편집거리, 용어/수치/부정, 구조화 평가 |
| `medspeech/runner.py`, `cli.py` | smoke/full 실행과 환경·예측·지연시간 저장 |
| `medspeech/api.py` | 업로드 검증, 추론, JSON/근거 검증, 보관 금지 |
| `tests/` | 누수, QC 결함, CER, JSON/환각, 후처리, API 오류 테스트 |
| `data/smoke/` | 실행된 fixture manifest, WAV, QC CSV/요약 |
| `artifacts/smoke/` | 실제 smoke 계산 결과·예측·환경·API 증거 |
| `artifacts/full/` | 실제 LoRA 체크포인트·로그, STT/LLM 예측·지표·지연시간·모델 SHA |
| `reports/` | 연구 보고서, 업무 매핑, 라이선스, QC 예시, 실행 기록 |

MMS 음성 사용·공유 조건은 [data_license.md](reports/data_license.md), 오류 검수 기준은 [qc_examples.md](reports/qc_examples.md)를 확인하세요. [Whisper 모델 카드](https://huggingface.co/openai/whisper-tiny), [Qwen 모델 카드](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct)의 모델 명칭·라이선스를 확인했습니다.

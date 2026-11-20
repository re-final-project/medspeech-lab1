# 뇌실 통로 폐쇄 가상 사례 — 구현·실행·검증

실행일: 2026-11-20, Asia/Seoul. 기존 FastAPI·Whisper·로컬 Qwen 경로를 유지하고 로컬 단일 페이지를 추가했다. 기존 화면은 없었다. 실환자 정보와 실제 MRI 이미지는 사용하지 않았다. 원인 질환은 사용자가 제공한 시나리오 설정이며 모델의 진단이 아니다.

## 변경 파일과 진입점

| 파일 | 역할 |
|---|---|
| `medspeech/cases/aqueduct_obstruction.json` | reference/STT/가상 판독문/시나리오 질환을 분리한 기준 사례. STT는 null |
| `medspeech/demo.py` | 사례·실행 상태·증상·영상 텍스트 소견 스키마, 데모 API, TTS/실제 모델/로컬 서버 CLI |
| `medspeech/web/index.html`, `style.css`, `app.js` | 단일 페이지, SVG 개념도, 정상/폐쇄 전환, MRI 숨김, 근거 및 JSON 표시 |
| `medspeech/api.py` | 기존 `/infer` 모델 로더를 데모에서도 공유하고 `/demo` 경로 추가 |
| `pyproject.toml` | HTML/CSS/JS/사례 JSON의 package data 포함 |
| `tools/run_demo_windows_copy_cache.py` | 관리형 Windows의 선택적 Hugging Face 복사 캐시 실행 |
| `tests/test_demo.py` | 출처 경계·모델 미실행·부분 실패·JSON/근거 검증·API 테스트 |
| `tests/demo_dom.test.cjs`, `tests/fixtures/aqueduct_example.json` | 실제 HTML/JS를 JSDOM에서 실행하는 상태 전환 테스트 |
| `package.json`, `pnpm-lock.yaml` | 선택적인 Node DOM 테스트와 고정 개발 의존성 |
| `data/demo/aqueduct_patient.wav`, `.metadata.json` | 이 발화만을 입력한 실제 MMS TTS 합성 음성과 출처·SHA·길이 |
| `artifacts/demo/model_run.json` | 실제 Whisper/Qwen 실행 결과. 실패도 상태와 함께 보존 |
| `artifacts/demo/example_run.json`, `example_no_mri.json` | 모델 미실행 예시와 판독문 숨김 API 결과 |
| `reports/demo_verification.json`, `demo_pytest.txt`, `demo_dom.txt`, `demo_smoke.txt` | 실제 검증 명령·종료 코드·stdout·HTTP 확인 |
| `README.md`, `.gitignore` | 실행 안내 및 Node 임시 의존성 제외 |

## 실행 명령

일반적인 Windows PowerShell 환경에서 프로젝트 루트 기준:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m medspeech.demo serve --port 8765
# 브라우저: http://127.0.0.1:8765/demo/aqueduct
```

실제 모델은 기존 SHA lock과 `[full]` 설치를 사용한다.

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test,full]'
.\.venv\Scripts\python.exe -m medspeech.demo generate-audio
.\.venv\Scripts\python.exe -m medspeech.demo run
.\.venv\Scripts\python.exe -m medspeech.demo run --no-mri --output artifacts/demo/no_mri_run.json
.\.venv\Scripts\python.exe -m pytest -q
npm install
npm run test:ui
```

이 호스트에서는 기존 번들 Python과 작업 폴더의 의존성·캐시를 연결한 `work/run_demo_host.py`로 `generate-audio`, `serve --port 8765`, `run`을 실제 실행했다. `run`은 FastAPI TestClient로 실제 `/demo/api/run`을 호출한다. 테스트는 `pytest -q -s -p no:cacheprovider -p no:tmpdir tests`, `node tests/demo_dom.test.cjs`를 실행했고, 기존 smoke는 `medspeech.cli smoke --base .../work/demo-smoke-check`로 독립 scratch 경로에서 실행했다. 원래 STT 실험의 데이터·학습 로그·지표를 덮어쓰지 않았다. 명령 배열과 경과 시간은 `demo_verification.json`에 있다.

## 정보 경계와 화면 동작

기본 화면의 상태는 ‘가상 사례 · 교육용 시뮬레이션’, ‘수도관 폐쇄’, ‘예시 전사문 · 모델 미실행’이다. 예시 증상은 직접 작성한 주석으로 표시하며 LLM 실행 결과로 취급하지 않는다. 실제 모델 실행은 버튼을 누르거나 `demo run`을 실행한 경우에만 일어난다.

개념도는 측뇌실 → 제3뇌실 → 중뇌수도관 → 제4뇌실 순서의 연결을 간략화한 SVG다. 폐쇄 상태에서 종괴 압박 지점 앞에서 흐름 화살표를 멈추고 측뇌실·제3뇌실을 색상·크기·‘상류 확장’ 텍스트로 함께 강조한다. 정상 상태에서는 폐쇄·종괴·확장 표시를 제거하고 화살표가 제4뇌실까지 이어진다. 실제 해부학적 위치·크기·비율을 재현하지 않는다. 제4뇌실 크기에 관한 입력 소견도 만들어내지 않는다. 수도관 폐쇄와 상류 뇌실 확장의 개념은 [관련 연구 문헌](https://pmc.ncbi.nlm.nih.gov/articles/PMC8491054/)을 참고했으며, 이 페이지에 실제 환자 사례나 영상을 가져오지 않았다.

시나리오 질환명은 `case.scenario_diagnosis`에 저장되고 화면의 시나리오 설정 영역에서만 표시된다. LLM에는 실제 전사 문자열만 전달한다. 음성 결과 스키마에는 증상만 있으며, 기존 Consultation 스키마와 전사문 근거 검증을 먼저 거친다. 가상 MRI 텍스트는 별도의 고정 범위 문자열 근거 추출을 사용한다. ‘폐쇄 관련 위치’는 판독문에 실제로 있는 ‘압박’ 문장에 연결하고, 측뇌실·제3뇌실은 확장 문장에 연결한다. 이 추출은 LLM이나 영상 분석으로 표시하지 않는다.

판독문 숨김 시 화면의 원문·소견·근거와 표시/저장 JSON의 imaging 값을 제거해 ‘영상 정보 없음’을 보여준다. 서버의 `include_mri=false`도 원문과 소견을 null로 반환한다. 시나리오 개념도는 입력 소견과 별개의 설명이므로 남는다. 정상/폐쇄 전환은 가상 판독문이나 모델 출력을 다시 쓰지 않는다.

실제 STT를 호출하지 않으면 `stt_transcript=null`이다. STT가 완료되고 LLM이 실패하면 실제 전사는 보존하고 음성 구조화는 null로 둔다. 스키마 실패는 `execution.structure=schema_error`로 표시한다. 데모 API의 HTTP 200은 상태 응답 수신을 뜻하며, 구조화 성공 조건은 `execution.structure=completed`다. 기존 `/infer`의 잘못된 모델 출력에 대한 HTTP 502 동작은 유지했다.

## 실제 모델 실행 결과

이 한 건의 정답 발화를 기존 `facebook/mms-tts-kor`에 입력하여 16 kHz 모노 PCM 합성 WAV를 생성했다. 길이는 **3.568초**다. TTS 조건과 라이선스는 WAV 옆 metadata 및 `data_license.md`에 기록했다. 실제 환자 녹취가 아니다.

| 항목 | 실제 관측 |
|---|---|
| 정답 전사 | 머리가 계속 아프고 구토도 했어요. |
| 실제 Whisper tiny 출력 | ` 머리가 계속 아프고, 굳어도 했어요.` |
| STT 단계 | completed |
| 로컬 모델 | Qwen/Qwen2.5-0.5B-Instruct / CPU dynamic INT8 |
| 구조화 단계 | **schema_error** |
| 음성 구조화 결과 | null — 예시 정답으로 대체하지 않음 |
| STT 시간 | 2.734108초 |
| 구조화 시간 | 3.197340초 |
| STT RTF | 0.766286 |

CPU는 Intel i5-1130G7, PyTorch 2.6.0+cpu, threads=2였다. 이 데모 호출에는 별도 워밍업을 하지 않았으며, 모델 초기 로딩 시간은 단계 타이머에 포함하지 않는다. 모델 이름과 고정 SHA는 기존 full 실험 파일을 사용했다. LLM은 기존 256-token 상한·JSON 접두사 fail-fast 설정을 그대로 사용했다. 구조화 지연시간은 유효 JSON 생성에 성공한 시간이 아니라 실패를 판정한 파이프라인 시간이다. n=1의 관측이며 성능 일반화를 하지 않는다.

정답 문자열의 ‘구토’와 달리 실제 전사에는 ‘굳어’가 나왔다. 합성 음성의 수동 청취 검수는 하지 않았으므로 TTS 발음 자체의 오류 가능성을 배제하지 않는다. 이 사례로 실제 임상 STT 또는 진단 능력을 주장하지 않는다. 질환 후보 순위·진단 확률·치료 추천·실제 MRI 분석은 구현하지 않았다.

첫 CLI 모델 실행은 결과 JSON 저장 뒤 Windows CP949 stdout의 em dash 인코딩 오류로 비정상 종료했다. CLI stdout을 UTF-8로 설정한 후 재실행하여 종료 코드 0을 확인했고, 위 수치는 그 최종 실행의 저장 JSON에서 읽었다.

## 검증 결과와 제한

- Python: 기존 21개를 포함한 **36개 테스트 통과**. 스키마 오류·근거 오류·STT 실패·모델 환경 부재·MRI 숨김·입력 출처 분리를 확인했다.
- DOM: **5개 테스트 통과**. 실제 HTML/JS를 JSDOM에서 실행하여 정상/폐쇄의 화살표·폐쇄 마커·상류 확장 상태, MRI 숨김/복원 및 JSON 저장, 구조화 실패·초기화·모델 미실행·네트워크 오류 후 화면 동작을 확인했다.
- 기존 smoke: **종료 코드 0**. QC·지표·JSON·API 경로를 scratch에서 끝까지 실행했다.
- 실제 HTTP: `/demo/aqueduct`, 예시 API, MRI 숨김 API, 합성 음성, `/health`, `/docs`가 모두 200이었다.
- **실제 브라우저 시각·클릭 검증은 미완료**다. 앱 내 브라우저는 초기화 시간 초과를 냈고, Edge 검증용 새 탭에서 주소 입력 후 Computer Use가 “현재 URL을 정책 적용에 충분한 확신으로 확인할 수 없다”는 이유로 탐색을 차단했다. 이후 UI 조작이나 다른 브라우저 제어 수단을 시도하지 않았다. DOM 테스트는 픽셀 렌더링·실제 브라우저·모바일 기기의 시각 QA를 대체했다고 주장하지 않는다. 수동 브라우저 확인이 남아 있다.

API는 원음·전사를 지속 보관하지 않는다. 이 실험의 CLI 기록은 가상 사례만 별도 산출물에 저장한다. 검증용 로컬 서버는 확인 후 종료하며, 사용자는 README 명령으로 다시 시작할 수 있다.

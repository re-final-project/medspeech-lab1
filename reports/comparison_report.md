# 전사 오류 비교 — 구현·실행·검증

검증일: **2026-11-22 (Asia/Seoul)**. 기존 「뇌실 통로 폐쇄 가상 사례」 단일 페이지와 실행 경로에 비교 영역을 추가했다. 기존 긍정 발화, 합성 음성, STT 실험 결과는 유지했다. 송과체 부위 생식세포종(germinoma)은 기존 시나리오 설정이며, 증상에서 추정한 결과가 아니다.

## 변경 파일

| 경로 | 변경 |
|---|---|
| `medspeech/comparison.py` | 비교 스키마·문자 diff·증상 상태 매핑·기존 LLM/스키마 재사용·API·합성/실제 실행 CLI |
| `medspeech/demo.py` | 기존 앱의 모델 제공자를 비교 API에서도 공유 |
| `medspeech/web/index.html` | 같은 페이지에 비교 영역·편집·실제 실행·모의 예시 선택 추가, 개념도에 ‘가상 시나리오’ 표시 |
| `medspeech/web/comparison.js`, `comparison.css` | 두 열 비교(좁은 화면은 세로), 다른 구간 강조, 근거·모델 실패·예시 정답 분리 |
| `data/demo/comparison_patient.wav`, `.metadata.json` | 부정 발화용 별도 TTS 합성 음성 및 출처 |
| `artifacts/comparison/model_run.json` | 실제 STT 출력과 원본/전사 각각의 구조화 실행 상태 |
| `tests/test_comparison.py` | 부정 반전, 부정 범위, MRI 독립성, 빈 입력, JSON 오류, 이전 음성 혼용 방지, 저장 결과 출처 |
| `tests/comparison_dom.test.cjs`, `tests/fixtures/transcription_comparison.json` | 실제 HTML/JS 기반 전환·강조·숨김·빈 전사·스키마 오류·네트워크 실패 검증 |
| `tools/run_comparison_windows_copy_cache.py` | 선택적인 관리형 Windows 모델 캐시 호환 진입점 |
| `README.md`, `package.json` | 실행·모델/예시 출처 안내, DOM 테스트 진입점 확장 |
| `reports/comparison_verification.json`, `comparison_*.txt` | 실제 테스트·HTTP 확인 명령과 종료 코드 |
| `reports/comparison-browser-checks.json`, `comparison-preview.jpg`, `comparison-detail.jpg` | 실제 브라우저 클릭·DOM 확인 기록 및 화면 |

## 실행 명령

기존 설치 환경의 프로젝트 루트에서:

```powershell
.\.venv\Scripts\python.exe -m medspeech.demo serve --port 8765
# http://127.0.0.1:8765/demo/aqueduct
.\.venv\Scripts\python.exe -m medspeech.comparison generate-audio
.\.venv\Scripts\python.exe -m medspeech.comparison run
.\.venv\Scripts\python.exe -m pytest -q
npm run test:ui
```

실제 모델 실행에는 기존 `[full]` 설치와 모델 SHA 설정이 필요하다. 관리형 Windows에서 복사 캐시가 필요하면 `python tools/run_comparison_windows_copy_cache.py generate-audio` 및 `... run`을 사용한다. 이 호스트에서는 번들 Python과 이미 설치된 `work/packages`, `work/full-packages`, `work/hf-cache`를 연결한 `work/run_comparison_host.py generate-audio`, `... run`을 실행했다. 모델은 캐시에서 읽었으며 새 대역 모델을 넣지 않았다. 서버는 기존 `work/run_demo_host.py serve --port 8765`로 실행했다.

최종 테스트는 `pytest -q -s -p no:cacheprovider -p no:tmpdir tests`, `node tests/demo_dom.test.cjs`, `node tests/comparison_dom.test.cjs`로 실행했다. 기존 smoke는 `medspeech.cli smoke --base .../work/comparison-smoke-check`에서 끝까지 실행하여 기존 실험 산출물을 덮어쓰지 않았다. 정확한 명령 배열·종료 코드·경과 시간은 `comparison_verification.json`에 보존했다.

## 비교 출처와 기대 동작

| 항목 | 원본 | 모의 전사 |
|---|---|---|
| 문장 | 머리가 계속 아프고 구토는 안 했어요. | 머리가 계속 아프고 구토를 했어요. |
| 두통 예시 정답 | 있음 — 머리가 계속 아프고 | 있음 — 머리가 계속 아프고 |
| 구토 예시 정답 | 없음 — 구토는 안 했어요 | 있음 — 구토를 했어요 |

문자 단위 SequenceMatcher로 원문 그대로 비교한다. ‘는 안’과 ‘를’ 같은 차이 구간을 강조하며, 한쪽에 대응 문자가 없는 구간은 ∅로 표시한다. 공백·문장부호 차이도 보존한다. 실제 전사를 모의 부정 반전 문장으로 바꾸지 않는다.

구조화에는 기존 `LocalLLM.extract(text, "grounded")`, 엄격한 `Consultation` JSON 검증 및 `grounded()`를 재사용한다. `symptoms`는 있음, `denied_symptoms`는 없음, 추출되지 않은 두통/구토 항목은 언급 없음으로 매핑한다. 원본과 전사문을 각각 별도 호출하며, MRI 문장·시나리오 질환명은 LLM 입력으로 전달하지 않는다. 스키마/근거 검증 실패 시 `model_states`와 `model_json`은 null이며 성공으로 처리하지 않는다.

시연용 주석은 **예시 정답 · 한정 문자열 주석 · 모델 결과 아님**으로 별도 표시한다. 이 주석도 기존 Consultation/Evidence 스키마와 근거 검증을 거친다. 범위는 제시된 발화 표현이며, 일반 한국어 부정 해석·동의어 복원·오탈자 교정 모델이 아니다. 임의의 수정 문장에 대한 전문가 정답으로 간주하지 않는다. 실제 모델 결과가 유효한 경우에는 별도의 ‘실제 LLM 결과’ 영역에 표시한다.

빈 전사문은 언급 없음으로 채우지 않고 `empty_transcript`와 ‘평가 불가’를 표시하며, 모델을 로드하거나 호출하지 않는다. 직접 수정한 전사는 source=edited이고 STT 출력으로 저장하지 않는다. 모의 예시의 `stt_transcript`는 null이다. 실제 STT가 반환한 문자열만 `stt_transcript`에 기록한다. 실제 출력이 빈 문자열이면 그 빈 값을 보존하고 모의 문장으로 대체하지 않는다.

기본 GET은 full 의존성과 유효한 저장된 실제 결과가 있으면 ‘저장된 실제 STT 결과 · 현재 요청에서 모델 재실행 안 함’으로 보여준다. 모델 환경/결과가 없거나 smoke 모드이면 ‘모의 전사 오류 · STT 미실행’과 고정 예시를 보여준다. 모의 예시 버튼은 언제나 이 고정 문장으로 돌아간다. 웹 요청은 입력/전사를 지속 저장하지 않고, 가상 사례 CLI 실행만 JSON 실험 파일을 저장한다.

## MRI와 개념도의 경계

MRI 소견은 기존 가상 판독문에서만 가져온다. 중뇌수도관 위치는 압박 문장에, 측뇌실·제3뇌실 확장은 확장 문장에 근거를 붙인다. 전사문을 바꾸거나 비워도 이 소견은 바뀌지 않는다. 판독문을 끄면 원문과 영상 소견을 제거하고 ‘영상 정보 없음’을 표시하며, 비교 JSON의 `simulated_mri_report`와 `imaging_findings`도 null이다. ‘가상 시나리오 · 교육용 개념도’는 계속 남는다. 증상에서 폐쇄나 종양 종류를 추정하는 로직은 없다.

## 실제 모델로 실행한 범위

- 비교용 **부정 발화**를 `facebook/mms-tts-kor`에 입력하여 별도 16 kHz mono 합성 WAV **4.144초**를 생성했다. 기존 긍정 발화 WAV와 혼용되지 않도록 metadata의 원본 발화도 검사한다.
- 기존 `openai/whisper-tiny`를 실제 실행했다. 출력은 **` 머리가 계속 아프고, 구톤은 안 했어요.`**였다.
- 원본과 실제 전사문 각각에 기존 `Qwen/Qwen2.5-0.5B-Instruct/cpu-dynamic-int8` 구조화를 실행했다. **양쪽 모두 schema_error**였고 실제 모델의 증상 상태는 null로 기록됐다.
- 실제 결과에서 요청된 ‘구토 없음 → 있음’ 반전이 관측됐다고 주장하지 않는다. 그 반전은 고정된 **모의 전사 오류**에서만 시연한다.
- 실제 전사에 있는 ‘구톤’은 한정 규칙의 ‘구토’와 일치하지 않아 예시 주석에서는 ‘언급 없음’으로 표시된다. 이는 실제 환자의 구토 여부 판정이 아니며, LLM이 추출한 결과도 아니다. 수동 청취 검수 없이 TTS와 STT 중 어느 단계의 발음/인식 오류인지 단정하지 않는다.

모델 이름·고정 SHA와 디코딩 설정은 기존 `configs/full.json`, `artifacts/full/model_revisions.json`을 사용했다. 이번 변경에서 STT 재학습, 진단 모델, 실제 MRI 분석, 실제 환자 데이터 평가는 실행하지 않았다.

## 검증 결과

| 검증 | 결과 |
|---|---|
| Python 기존·추가 테스트 | **50개 통과** |
| 기존 데모 DOM 테스트 | **5개 통과** |
| 추가 비교 DOM 테스트 | **5개 통과** |
| 기존 smoke | **종료 코드 0** |
| 화면·JS·비교 API·모의 API·MRI 숨김 API·문서 HTTP | 모두 **200** |
| 실제 브라우저 | **연결·클릭·DOM·화면 확인 완료** |

2026-11-22 앱 내 브라우저에서 저장된 실제 STT 결과와 두 JSON 오류 상태를 확인했다. 모의 예시 버튼으로 두통 양쪽 있음, 구토 원본 없음/전사 있음, 근거 문구와 강조 구간을 확인했다. 정상 흐름에서는 하류 화살표가 나타나고 종괴/확장 마커가 사라짐을 확인했다. 수도관 폐쇄로 돌아간 후 MRI 숨김 시 ‘영상 정보 없음’과 null JSON, 남아 있는 개념도를 확인했다. 빈 전사문 적용 시 평가 불가를 확인했고, 모의 문장과 MRI를 복원했다. 이 과정은 현재 기본 브라우저 폭에서 확인했으며 모든 장치/화면 크기의 시각 QA를 주장하지 않는다.

브라우저 상태 확인은 `comparison-browser-checks.json`, 전체 화면은 `comparison-preview.jpg`, 두 비교 카드 화면은 `comparison-detail.jpg`에 남겼다. 검증용 로컬 서버는 확인 후 종료하며 README 명령으로 다시 시작할 수 있다.

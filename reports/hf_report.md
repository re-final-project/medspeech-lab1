# Hugging Face 모델 연결 및 검증

## 구현과 출처

교육용 가상 전사만 HF Inference Providers로 보내는 `InferenceClient` 어댑터를 추가했다. 기본 모델은 Qwen/Qwen3-32B, 제공자는 DeepInfra이며 환경변수로 교체할 수 있다. [HF Structured Outputs 공식 문서](https://huggingface.co/docs/inference-providers/guides/structured-output), [모델 페이지](https://huggingface.co/Qwen/Qwen3-32B), [공식 모델·제공자 메타데이터 API](https://huggingface.co/docs/inference-providers/hub-api)를 구현 전에 확인했다. 공개 모델 목록에서 DeepInfra의 이 모델이 live이며 supports_structured_output=true임을 확인한 응답을 `artifacts/hf/provider_check.json`에 보존했다. 호출 시에도 지원을 재확인하며 자동 제공자 선택을 하지 않는다. 문서 예시의 Cerebras는 현재 모델 가용성의 증거로 사용하지 않았다.

기존 수정문 재분석, 새 초기 전사 분석, LoRA/Turbo 전사 분석은 동일 API와 Qwen 어댑터를 사용한다. 두 증상을 고정 키로 지정한 Pydantic 스키마와 기존 Consultation/Evidence/grounded 계약을 함께 사용한다. JSON 키 누락·추가·중복, evidence null 규약, 입력에 없는 근거, 증상 없는 근거, 제한적인 한국어 부정 충돌을 검증한다. MRI 및 시나리오 질환은 사용자 메시지나 시스템 프롬프트에 포함하지 않는다. 모델 토큰·상위 서비스 예외 원문은 응답이나 로그에 담지 않는다.

버전은 입력 종류와 본문의 SHA256으로 표시하고 실행은 UUID로 구분한다. 같은 본문의 재실행은 같은 입력 해시와 다른 실행 ID를 갖는다. 이는 영구 DB 버전 이력이 아니며 브라우저 새로고침을 넘는 모든 편집 이벤트 보존은 설계안이다. README ERD에 제공자·입력 버전·스키마 통과 여부를 추가하고 구현과 제안 테이블을 구분했다. 기존 로컬 모델 배치 실험과 `/infer`는 유지한다.

## 실제 실행 결과

Windows 11, PyTorch 2.6.0+cpu, torch 스레드 2, 워밍업 없음. 상세 CPU 식별자·모델 SHA·체크포인트·입력 해시는 `artifacts/hf/verification.json`에 있다. 같은 비교용 TTS WAV **4.144초**를 사용했다. 음성 SHA256은 두 모델 모두 `ad580be9bc67335f8b3185c6d19cdfec045727969862dc13e4a652b165eb6589`다. 기준 발화는 「머리가 계속 아프고 구토는 안 했어요.」다. 두 STT 모두 language=ko, task=transcribe, beam=1, greedy, max_new_tokens=128로 실행했다.

| 실제 STT | 실제 출력 | CER (기존 normalize·공백 제외) | 전사 시간 | RTF |
|---|---|---|---|---|
| 기존 Whisper tiny + LoRA | ` 머리락에서 갚고 구톤은 안 했어요.` | 43.75% | 1.288초 | 0.311 |
| Whisper large-v3-turbo | ` 머리라 계속 아프고 구토는 안 했어요.` | 6.25% | 176.071초 | 42.488 |

전사 시간은 모델 로딩·다운로드를 제외한 실제 generate+decode 시간이다. Turbo의 첫 호출에는 워밍업하지 않은 상태가 반영되며 CPU에서 매우 느렸다. 위 시간은 반복 평균이나 서비스 지연시간 보장이 아니다. 이 표는 가상 발화 한 건(n=1)의 실제 모델 결과이며 고정 테스트 6개인 기존 학습 실험 표와 합치지 않는다. 합성 발화 한 건의 CER 차이를 실제 진료 성능이나 모델 전체의 우열로 일반화하지 않는다. 이번에 추가 학습은 실행하지 않았다.

**실제 Qwen3 추출은 미검증이다.** 서버 환경에 HF_TOKEN이 없었다. 긍정/부정 지정 문장 및 두 실제 STT 출력 모두 Qwen 경로까지 연결했지만 `unavailable / token_missing`으로 종료했다. `schema_valid`, `symptom_states_correct`, `symptom_output`은 null이다. 이 상태는 스키마 실패나 모델이 틀린 증상 상태를 출력한 것과 다르다. DeepInfra의 공개 지원 메타데이터 확인은 인증된 실제 추론 성공을 뜻하지 않는다.

## 모의 응답 검증 (실제 성능과 분리)

- 「머리가 계속 아프고 구토를 했어요」: headache=present, vomiting=present가 기대값이다.
- 「머리가 계속 아프고 구토는 안 했어요」: headache=present, vomiting=absent가 기대값이다.
- 두 문장에 대한 모의 InferenceClient 응답은 JSON 스키마와 기대 증상 상태 검사를 각각 통과했다. `artifacts/hf/mock_validation.json`은 모의 응답임을 명시한다.
- 입력에 없는 인용 구절은 grounding_error로 거부한다. 스키마는 통과했어도 이 경우 실행 실패이고 증상 결과는 null이다. 중복/누락/추가 코드와 null 규약은 schema_error, 제한적인 부정 충돌은 content_error로 거부한다.
- not_mentioned에 null을 강제한다. 이 검증만으로 의미상 잘못된 미언급 판정이나 모든 한국어 부정 범위 오류를 검출한다고 주장하지 않는다.

최종 회귀 검증은 **Python 75개, DOM 19개 통과**, smoke 종료 코드 0이다. `reports/hf_*txt`, `reports/hf_verification.json`에 명령과 종료 코드를 남겼다. 테스트는 provider 지원·토큰 누락·호출 실패의 안전한 오류, 실제 모델명/입력 버전 표시, 같은 WAV 사용, CER, 미실행 STT null, 기존 정상/폐쇄·MRI 숨김·수정문 재편집 경로도 포함한다. 분리된 SDK worker의 입력·오류 재검증과 smoke에서 실제 모델을 호출하지 않는 것도 검사했다. 모의 응답 테스트는 실제 Qwen 정확도가 아니다.

브라우저에서는 초기와 수정문에 서로 다른 입력 버전이 표시된 HF_TOKEN 누락 응답, 재시도 가능 상태, LoRA 실제 STT 출력과 동일 Qwen 오류, Turbo 선택·미실행 상태, 모의 결과의 구토 있음→없음 표시를 확인했다. Turbo는 CLI에서 실제 실행했으며 브라우저에서 긴 추론을 반복하지 않았다. `hf-review.jpg`와 `hf-mock-review.jpg`에 실패/모의 화면을 따로 남겼다.

## 실행 명령

정상 설치 환경은 README의 환경변수 설정 후 다음을 실행한다.

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test,full]'
py -3.12 -m venv .venv-hf
.\.venv-hf\Scripts\python.exe -m pip install -e '.[hf]'
$env:HF_CLIENT_PYTHON = (Resolve-Path '.\.venv-hf\Scripts\python.exe').Path
.\.venv\Scripts\python.exe -m medspeech.demo serve --port 8765
.\.venv\Scripts\python.exe -m medspeech.hf_demo --stt both --output artifacts/hf/verification.json
.\.venv\Scripts\python.exe -m pytest -q
npm run test:ui
```

이번 관리형 호스트에서는 PATH에 Python·npm이 없어 번들 Python과 직접 Node를 사용했다. 기존 `work/packages`, `work/full-packages`, `work/hf-cache`를 연결하고 HF symlink 대신 파일 복사를 사용한 호스트 래퍼를 실행했다.

호환성 확인 중 기존 HF SDK 0.29.3과 0.36.0에 DeepInfra 어댑터가 없음을 확인했다. 기존 Transformers 4.49는 hub<1을 요구하므로 HF SDK를 같은 환경에서 덮어쓰지 않았다. 새 `hf` extra는 **hub 1.24.0**을 별도 환경에 설치하고 `HF_CLIENT_PYTHON` worker를 통해 호출한다. 호스트에서는 PyPI 공식 wheel의 SHA256을 확인해 별도 경로에 추출하고 실제 1.24.0 InferenceClient의 DeepInfra 요청 생성과 strict JSON Schema 전달을 검사했다. 응답은 가로챈 모의 응답이며 모델 추론은 하지 않았다. 이 독립 SDK 검증은 `artifacts/hf/client_sdk_check.json`에 있다. 실제 STT 실행의 SDK 버전과 혼용하지 않는다.

```powershell
$python = 'C:\Users\정준하\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python -u work/run_hf_host.py --stt both --output work/publish-medspeech-lab1/artifacts/hf/verification.json
& $python -u work/run_demo_host.py serve --port 8765
& $python work/verify_hf.py
& $python work/check_hf_sdk.py
```

`verify_hf.py`는 저장소에서 pytest와 네 DOM 파일을 각각 실행하고, 기존 smoke를 별도 `work/hf-smoke-check`에 실행하여 기존 실험 결과를 보존했다. 정확한 하위 명령은 `hf_verification.json`에 있다. Qwen 실제 호출 재현에는 서버의 HF_TOKEN 및 사용 가능한 Inference Providers 권한/잔액이 필요하다. 토큰은 보고서에 기록하지 않는다.

## 변경 파일

- `medspeech/hf_models.py`, `hf_worker.py`, `hf_demo.py`: 외부 어댑터·스키마·근거 검증·분리된 SDK 프로세스·재현 CLI.
- `medspeech/review.py`, `api.py`, `demo.py`: 기존 검토 버튼 연결과 실행 식별자·오류 상태.
- `medspeech/stt_compare.py`: 동일 가상 WAV의 LoRA/Turbo 실행, 기존 CER, revision·RTF.
- `medspeech/web/index.html`, `review.js`, `review.css`, `stt-options.js`, `app.js`, `comparison.js`: 초기·수정 분석, STT 선택·비교, 모의 결과 표시.
- `tests/test_hf_models.py`, `tests/hf_dom.test.cjs`, `package.json`, `pyproject.toml`: 검증과 선택 의존성.
- README, `configs/two_symptoms.schema.json`, `artifacts/hf/`, 본 보고서·로그·화면 및 파일 매니페스트.

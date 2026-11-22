# 전사 검토 및 수정 실행 보고

기존 가상 사례·비교 화면에 검토 영역을 추가했다. 초기 전사와 구조화 결과를 스냅샷으로 보존하고 수정문만 기존 Consultation 스키마·근거 검증에 전달한다. 가상 사례·교육용이며, 진단이나 치료 추천을 수행하지 않는다.

## 변경 파일

- `medspeech/review.py`: 세션·수정문 API, 엄격한 요청/응답 스키마, 실제·예시·실패 분리, CLI.
- `medspeech/demo.py`: 기존 FastAPI 진입점에 검토 라우트 연결.
- `medspeech/web/index.html`, `review.js`, `review.css`: 세 입력, 상태·근거·변경 강조, 재편집 기준 표시, 빈 입력 차단, 재시도.
- `tests/test_review.py`, `tests/review_dom.test.cjs`, `tests/fixtures/review_example.json`, `package.json`: API·스키마·UI 회귀 검증.
- `tools/run_review_windows_copy_cache.py`, README, 업무 매핑, 본 보고서와 검증 로그·실험 JSON.

## 실행 명령과 결과

정상 설치 환경의 PowerShell 명령은 README와 같다. 이번 관리형 호스트에서는 Python 실행 파일이 PATH에 없어 번들 Python을 사용하고, `work/packages`·`work/full-packages`를 PYTHONPATH에 연결했다. `work/run_review_host.py`와 `work/run_demo_host.py`는 캐시 경로·offline 모드·CPU 스레드 2·파일 복사 캐시만 설정한 호스트용 래퍼다.

```powershell
$python = 'C:\Users\정준하\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python -u work/run_review_host.py run
& $python -u work/run_review_host.py run --example --output work/publish-medspeech-lab1/artifacts/review/example_run.json
& $python -u work/run_demo_host.py serve --port 8765
# 저장소 폴더에서 실행한 테스트 (호스트에서는 의존성 PYTHONPATH 지정)
& $python -m pytest tests -q -s -p no:cacheprovider -p no:tmpdir
node tests/demo_dom.test.cjs
node tests/comparison_dom.test.cjs
node tests/review_dom.test.cjs
# 기존 결과를 덮어쓰지 않도록 별도 scratch base에서 실행
& $python -m medspeech.cli smoke --base work/review-smoke-check
```

Python **59개 통과**, DOM **16개 통과(기존 10+추가 6)**, smoke 종료 코드 **0**. 로그는 `review_pytest.txt`, `review_dom.txt, review_comparison_dom.txt, review_new_dom.txt`, `review_smoke.txt`에 있다. smoke는 대역 STT·LLM이며 성능을 실제 모델 성능으로 주장하지 않는다. fixture_A/B 각각 n=6, CER=0.043010752688172046은 기존 계산 경로 회귀 확인값이다.

브라우저에서 모의 시연 시작→부정 수정문 채우기→재분석을 직접 실행하여 두통 **있음→있음**, 구토 **있음→없음** 및 각 입력 근거를 확인했다. 공백으로 재편집하면 버튼이 비활성화되고 이전 결과에 **이전 수정문 기준**이 표시된다. 정상 흐름/폐쇄 복원, MRI 숨김 시 영상 정보 없음 및 표시 복원을 확인했다. `review-screen.jpg`는 확인한 전체 화면이다. DOM 테스트는 응답 대기 중 편집 보존, 실패 후 재시도, 스키마 오류를 성공으로 처리하지 않음, MRI JSON 제거도 검사한다. 모든 장치·폭에서의 시각 검증을 주장하지 않는다.

## 실제 모델 실행 범위와 한계

`artifacts/review/reanalysis_run.json`은 기존 Qwen/Qwen2.5-0.5B-Instruct CPU dynamic INT8를 수정문 **머리가 계속 아프고 구토는 안 했어요.**에 실제 실행한 결과다. 기존 체크포인트·SHA 고정을 재사용했다. 결과는 **failed / schema_error**이며 실제 model_states, model_json, example_answer는 모두 null이다. 실패를 예시 값으로 대체하지 않았다. 성공적인 실제 추출이나 정확도 개선을 주장할 수 없다.

`artifacts/review/example_run.json`은 별도 **예시 결과**다. 구토 없음은 지정 문장에 붙인 시연용 정답이며 LLM 성능이 아니다. 실제 실패 후에도 사용자는 재시도하거나 명시적인 모의 시연으로 전환할 수 있다.

이번 작업에서는 STT/TTS를 재실행하지 않았다(`stt_executed=false`). 실제 초기 전사는 이전 비교 실험의 Whisper tiny 출력이며 저장 결과라는 레이블을 유지한다. 수정문 API는 STT를 호출하지 않는다. 모델 공급자 초기화에서 Whisper 객체가 로드되더라도 음성 추론은 수행하지 않는다. 재학습·실환자·의료영상 분석·진단 확률 평가는 실행하지 않았다. MRI 소견은 가상 판독문 문자열 근거에서만 가져오며 증상에서 추론하지 않는다. 합성 사례 결과를 실제 진료 성능으로 일반화하지 않는다.

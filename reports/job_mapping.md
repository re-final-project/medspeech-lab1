# 의료 STT·LLM R&D 업무 대응

구체적인 채용공고 원문은 제공되지 않았다. 아래 담당업무는 요청에 명시된 역할을 기준으로 구성했으며 특정 회사의 공고를 인용한 것이 아니다. smoke는 연구 인프라 검증 증거로만 제시한다. 실제 학습 실적은 실험 보고서의 실행 상태와 함께 제시해야 한다.

이 제출물에서는 실제 CPU LoRA 학습 3 epochs와 A/B/C 평가를 완료했다. 구조화는 실제 로컬 LLM의 스키마 실패까지 측정했으며, 추출 품질이 해결됐다고 주장하지 않는다.

| 담당업무/역량 | 구현 코드 | 실험 증거 | 보고서 항목 |
|---|---|---|---|
| 한국어 의료 음성 데이터 구축 | `medspeech/data.py:CASES, build`, `adapters.py:MMSTTS` | `data/smoke/manifest.jsonl`, full 실행 시 `data/full/` | 실험 보고서 데이터 구성; `data_license.md` |
| 품질검수와 누수 방지 | `data.py:qc`, `tests/test_core.py` | `data/smoke/qc.csv`, `qc_summary.json` | QC 및 화자 중복; `qc_examples.md` |
| PyTorch 모델 학습 | `training.py:train` | `artifacts/full/checkpoints/training_log.json`, `training_config.json`, `best/` | 실제 모델 실행 상태와 한계 |
| STT 기준선/후처리/LoRA 비교 | `runner.py:full`, `adapters.py:WhisperAdapter, fit_rules` | `artifacts/full/metrics.json`, `stt_predictions.json`, `postprocess_audit.json` | 연구 질문, 모델과 비교 조건 |
| CER 중심 평가와 오류 분석 | `metrics.py`, `runner.py:evaluate` | `artifacts/smoke/metrics.json`, `extraction_predictions.json` | smoke 수치와 대표 오류; 실제 모델과 구분 |
| LLM 구조화 및 근거 검증 | `schema.py`, `adapters.py:LocalLLM`, `metrics.py:extraction_metrics` | prompt/입력별 지표와 raw 출력 | 스키마 통과와 내용 오류의 차이 |
| 음성→텍스트→구조화 오류 전파 | `runner.py:evaluate` | gold vs fixture_A/B 결과, full 실행 시 gold vs A/B/C | 수치 오인식·부정 반전 사례 |
| 추론 서비스 | `api.py:create_app` | `artifacts/smoke/api_smoke.json`, API pytest | API 검증과 보관 정책 |
| 교육용 사례 UI·출처 분리 | `demo.py`, `web/`, `tests/test_demo.py`, `tests/demo_dom.test.cjs` | `artifacts/demo/model_run.json`, `reports/demo_verification.json` | `demo_report.md`: 모델 미실행/실패·MRI 숨김·근거 경계 |
| 부정 표현 전사 오류·증상 상태 비교 | `comparison.py`, `web/comparison.js`, `tests/test_comparison.py` | `artifacts/comparison/model_run.json`, `reports/comparison_verification.json` | `comparison_report.md`: 실제/모의 전사·예시 정답·MRI 독립성 |
| 전사 검토·수정 및 재분석 상태 관리 | `review.py`, `web/review.js`, `tests/test_review.py`, `tests/review_dom.test.cjs` | `artifacts/review/`, `reports/review_verification.json` | `review_report.md`: 초기 보존·stale·실패/예시 구분 |
| 재현 가능한 실험 관리 | `cli.py`, `configs/full.json`, `adapters.py:resolve` | 환경·설정·모델 SHA·샘플 ID·실패 증거 | 실행 기록과 미실행 항목 |

면접에서 설명할 핵심: 스키마 통과와 원문 근거 존재가 정답 보존을 보증하지 않는다. 38.2→32.8처럼 STT가 수치를 바꾸면 추출기는 잘못된 수치를 근거 있게 반환할 수 있다. 따라서 STT 오류와 추출기 자체 오류를 별도 입력 조건으로 측정해야 한다.

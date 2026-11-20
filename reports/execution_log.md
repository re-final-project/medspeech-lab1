# 실제 실행 기록

실행일: 2026-11-20, Asia/Seoul. 시작 디렉터리에는 outputs/와 work/만 있었고 기존 소스·Git 저장소·적용할 AGENTS.md가 없었다. 기존 사용자 파일은 수정하지 않았다. 완성 프로젝트는 outputs/medspeech-lab/에 작성했다.

## 환경 설치와 문제 해결

호스트 기본 PATH에 python 명령이 없어서 번들 Python 3.12.14를 사용했다.

```powershell
$python = 'C:\Users\정준하\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $python -m venv --system-site-packages work\venv
& $python -m pip --python .\work\venv\Scripts\python.exe install fastapi==0.115.12 httpx==0.28.1 python-multipart==0.0.20 pytest==8.3.5 soundfile==0.13.1 uvicorn==0.34.2
```

venv ensurepip는 관리형 Windows 임시 폴더 권한 문제로 실패했다. pip의 일반 설치도 임시 폴더 ACL 문제로 정상 진행되지 않아 중단했다. 추가 네트워크 권한을 받은 뒤 PyPI JSON API에서 해당 버전의 wheel URL·SHA256을 조회하고 표준 라이브러리 HTTPS로 내려받아 SHA256 검증 후 work/packages와 work/full-packages에 풀었다. 이는 프로젝트 밖 호스트 검증용 라이브러리다. 전체 의존성을 배포물에 동봉하지 않는다. 일반 환경에서는 README의 pip 설치 경로를 사용한다.

호스트에서 실행한 설치 대안:

```powershell
& $python work\bootstrap_wheels.py
& $python work\bootstrap_full.py
```

PyTorch 2.6.0+cpu 및 Transformers 4.49.0의 import를 확인했고 CUDA는 False였다. full 최초 모델 캐시 시도에서는 Hugging Face의 임시 디렉터리 symlink 검사가 PermissionError로 실패했다. 실패 증거는 artifacts/full/first_attempt_failure.json에 보존했다. 파일 복사 캐시 fallback으로 전환했고 모델 SHA를 artifacts/full/model_revisions.json에 고정했다.

## 테스트·smoke 실행

호스트의 실제 환경 연결:

```powershell
$env:PYTHONPATH = (Resolve-Path work\packages).Path + ';' + (Resolve-Path outputs\medspeech-lab).Path
& $python -m pytest -q -s -p no:cacheprovider -p no:tmpdir outputs\medspeech-lab\tests
& $python -m medspeech.cli smoke
& $python work\verify.py
```

테스트의 큰 bytes 매개변수에 자동으로 붙은 ID가 과도하게 길어지는 문제를 고쳤고, Windows 임시 폴더 ACL에 영향을 받지 않도록 테스트용 작업 경로를 명시했다. 최신 검증의 정확한 명령·종료 코드·경과 시간은 verification.json, stdout은 pytest.txt와 smoke.txt다. 최종 완료 기준은 이 기록의 exit_code=0이다.

## 실제 모델 실행

```powershell
$env:PYTHONPATH = (Resolve-Path work\full-packages).Path + ';' + (Resolve-Path work\packages).Path + ';' + (Resolve-Path outputs\medspeech-lab).Path
$env:HF_HOME = Join-Path (Get-Location) 'work\hf-cache'
$env:OMP_NUM_THREADS = '2'
$env:MKL_NUM_THREADS = '2'
& $python -m medspeech.cli full
# symlink probe 실패 후 동일 모델/설정의 복사 캐시 방식으로 재실행
& $python -u work\run_full_host.py full
```

동일한 호환 wrapper는 배포물의 tools/run_windows_copy_cache.py다. 실행 중 MMS의 숫자 토큰 제거 위험을 확인해 수치·단위·약어의 TTS 읽기 전처리를 추가했다. 수정 전 생성 음성으로 성능을 보고하지 않고 수정한 생성기로 재시작했다. Uroman 리소스 로딩을 문장마다 반복하지 않도록 한 번 생성해 재사용한다. 최종 모델 실행 상태는 artifacts/full/run_status.json 또는 failure.json을 기준으로 보고서에 반영한다.

STT 학습·비교를 완료한 후 CPU FP32 LLM의 교차 평가 지연이 길어 해당 시도를 중단했다. 설정에 `llm_cpu_int8=true`를 추가하고 동일 로컬 LLM의 Linear 동적 INT8 양자화로 구조화 단계만 실행했다. STT 예측·학습 체크포인트를 재사용했으며 모델 학습/테스트 분할과 후처리 규칙을 바꾸지 않았다. FP32 중단 시도는 최종 LLM 성능표나 지연시간에 포함하지 않는다.

```powershell
& $python -u work\run_full_host.py full --stage structure
```

INT8 512-token 첫 호출은 약 98.7초였고 JSON 대신 schema 관련 표를 생성했다. 이 중단한 탐색 출력은 artifacts/exploratory_int8_512/에 별도로 보존하며 최종 지표에 섞지 않는다. train/dev 정답 JSON의 tokenizer 길이(120~129 tokens)를 확인한 후 출력 상한을 256으로 줄이고, 완전히 동일한 전사+프롬프트의 greedy 결과를 재사용하도록 구현했다. 테스트를 본 뒤 프롬프트 문구나 용어 사전을 조정하지 않았다. 최종 프롬프트 비교는 동일한 INT8/256-token 설정에서 새로 실행했다. 캐시 반환은 모델 지연시간 표본에 포함하지 않는다.

256-token 실행 중, strict JSON 객체에서 첫 비공백 문자가 `{`가 아니면 이후 토큰과 무관하게 검증이 실패한다는 조건을 이용해 조기 중단을 추가했다. 기존 장문 실패 출력은 artifacts/exploratory_int8_256/에 보존했다. 최종 실행은 양 프롬프트 모두 같은 fail-fast 규칙을 적용한다. 이는 생성값을 수정하는 후처리가 아니며 유효 JSON을 거부하지 않는다. 실패 접두사·판정과 실제 조기 중단 지연시간을 기록한다.

## 산출물과 남은 검수

README, pyproject.toml, configs, medspeech 패키지, tests, tools, 가상 manifest·음성·QC CSV, artifacts, reports를 생성했다. 저장된 예측과 지표는 smoke/full 디렉터리로 분리한다. 데이터 청취 검수와 실제 환자 도메인 검증은 수행하지 않았다. 실제 환자·녹취는 사용하지 않았고 합성 결과의 임상 일반화를 주장하지 않는다. 의료용어 후처리의 개선이 없으면 그 사실을 그대로 보고한다.

## 최종 검증 결과

pytest 21개 통과, smoke 종료 코드 0. 실제 TTS 36개·QC 289건 실패 0·LoRA 3 epochs·고정 테스트 A/B/C 비교·LLM 8조건 평가를 완료했다. 최종 LLM은 CPU INT8 / 256-token 상한 / JSON 접두사 fail-fast다.

실제 CER: A=0.365591, B=0.365591, C=0.318996. STT RTF: A=0.277628, C=0.263566. 테스트 오디오 65.629초.

LLM 48개 평가 행, 실제 생성 28회, 동일 입력/프롬프트 캐시 20회. JSON 통과율: {"gold/basic": 0.0, "gold/grounded": 0.0, "A/basic": 0.0, "A/grounded": 0.0, "B/basic": 0.0, "B/grounded": 0.0, "C/basic": 0.0, "C/grounded": 0.0}.

미실행/중단 항목: GPU 실행(CUDA 미사용), 독립 화자 평가(단일 TTS 화자), 수동 청취 검수(상태 pending), 실제 환자 녹취 평가(연구 범위에서 제외), FP32 전체 교차 평가 및 512-token 자유 생성 전체 평가(CPU 비용으로 중단; 별도 탐색 파일 보존). 최종 INT8/fail-fast 결과를 그 설정들의 성능으로 해석하지 않는다.

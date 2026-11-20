# 합성 데이터와 재배포

확인일: 2026-11-20. 실제 환자 정보·실제 녹취를 사용하지 않는다. 문장과 정답은 이 프로젝트에서 작성한 가상 예시다. 진료 지침이나 처방 예시로 사용하지 않는다.

실제 음성 생성기는 Meta의 [facebook/mms-tts-kor 모델 카드](https://huggingface.co/facebook/mms-tts-kor/blob/main/README.md)에 명시된 CC BY-NC 4.0 모델을 사용한다. [CC BY-NC 4.0 조건](https://creativecommons.org/licenses/by-nc/4.0/)은 출처·라이선스 링크·변경 표시와 비상업적 사용을 조건으로 공유와 변형을 허용한다. 모델 가중치의 라이선스가 모든 출력물에 자동 적용된다고 단정하지 않는다. 이 프로젝트는 보수적으로 생성 음성에도 같은 비상업적 공유 조건과 출처 표시를 적용한다. 상업 서비스·상업 데이터셋으로 전용하려면 별도 권리 검토 또는 다른 TTS가 필요하다.

음성 출처 표시: “Synthetic Korean speech generated with Meta MMS Korean TTS (facebook/mms-tts-kor), CC BY-NC 4.0. Scripts and fictional text: medspeech-lab contributors. Modifications: 16 kHz mono PCM conversion, 20 dB white-noise augmentation, resampling-based 1.1x speed/pitch change.” 모델 SHA는 artifacts/full/model_revisions.json에 남는다. 음성 배포 시 이 파일과 본 문서를 동봉한다. TTS 가중치는 이 저장소에 재배포하지 않는다.

smoke의 WAV는 수학적으로 생성한 테스트 톤으로 TTS 출력·언어 음성이 아니다. smoke 결과로 음성인식 성능을 주장하지 않는다. MMS는 단일 합성 화자로 실제 화자 분리 평가가 불가능하며 속도 변형을 별도 화자로 세지 않는다.

TTS 발음은 정답 전사와 다를 수 있다. 숫자·영문·약어의 읽기 방식은 청취 검수 전까지 보증하지 않는다. review_status=automatic_pending_listening은 자동 QC만 통과했음을 뜻한다. 실제 성능 보고 전 수동 청취와 정답 수정 버전 발행이 필요하다.

MMS의 문자 어휘에는 숫자 기호가 없으므로 수치·단위·약어를 `medspeech/verbalize.py`로 읽기 문자열로 변환한 후 Uroman에 전달한다. 예: 38.2 도→삼십팔 점 이 도, 500 mg→오백 밀리그램. 약어·단위 확장은 TTS 입력에만 적용하며 STT 가설을 정답에 맞추는 후처리에는 사용하지 않는다. manifest의 tts_input에 실제 입력을 남긴다.

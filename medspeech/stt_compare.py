"""Two local STT adapters processing the exact same fixed fictional WAV."""
import hashlib
import json
import os
import time
import threading
from pathlib import Path
from typing import Literal
import soundfile as sf
from pydantic import BaseModel, ConfigDict
from .comparison import AUDIO_PATH, REFERENCE
from .demo import ROOT
from .metrics import normalize, distance


def load_stt(choice):
    from .adapters import WhisperAdapter
    config = json.loads((ROOT/'configs/full.json').read_text(encoding='utf-8'))
    revisions = json.loads((ROOT/'artifacts/full/model_revisions.json').read_text(encoding='utf-8'))
    if choice == 'lora':
        checkpoint = Path(os.getenv('MEDSPEECH_LORA_PATH', str(ROOT/'artifacts/full/checkpoints/best')))
        if not (checkpoint/'adapter_config.json').exists():
            raise FileNotFoundError('LoRA checkpoint missing')
        model = WhisperAdapter(config, revisions, str(checkpoint))
        model.name += '/LoRA'
        model.checkpoint = str(checkpoint)
    else:
        config = dict(config, stt='openai/whisper-large-v3-turbo')
        from huggingface_hub import HfApi
        revision = os.getenv('HF_TURBO_REVISION') or HfApi().model_info(config['stt']).sha
        revisions = dict(revisions, stt=revision)
        model = WhisperAdapter(config, revisions)
        model.checkpoint = None
    model.revision = revisions['stt']
    return model


class STTRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    choice: Literal['lora', 'turbo'] = 'lora'


def transcribe_case(choice, factory=load_stt):
    name = 'openai/whisper-tiny/LoRA' if choice == 'lora' else 'openai/whisper-large-v3-turbo'
    result = dict(choice=choice, model=name, status='not_run', label='미실행', transcript=None,
                  cer=None, input_version=None, audio_sha256=None, reference_transcript=REFERENCE,
                  revision=None, checkpoint=None)
    try:
        audio, rate = sf.read(AUDIO_PATH, dtype='float32')
        if rate != 16000 or audio.ndim != 1:
            raise ValueError('invalid fixed WAV')
        # Match the reference metadata used by the existing comparison demo.
        metadata = json.loads(AUDIO_PATH.with_suffix('.metadata.json').read_text(encoding='utf-8'))
        if metadata['reference_transcript'] != REFERENCE:
            raise ValueError('reference mismatch')
        result.update(audio_sha256=hashlib.sha256(AUDIO_PATH.read_bytes()).hexdigest(), audio_seconds=len(audio)/rate)
        model = factory(choice)
        result.update(model=model.name, revision=getattr(model,'revision',None), checkpoint=getattr(model,'checkpoint',None))
        start = time.perf_counter()
        text = model.transcribe(audio)
        seconds = time.perf_counter()-start
        if not isinstance(text,str) or not text.strip():
            raise ValueError('empty STT')
        from .hf_models import input_version
        gold = normalize(REFERENCE).replace(' ',''); pred = normalize(text).replace(' ','')
        result.update(status='completed',label='실제 STT 결과',transcript=text,
                      cer=distance(gold,pred)/max(len(gold),1),input_version=input_version(text,'stt_'+choice),
                      stt_seconds=seconds,rtf=seconds/result['audio_seconds'])
    except Exception:
        result.update(status='unavailable',label='미실행 또는 실행 실패 · 모델/체크포인트·음성 환경 확인',error_code='stt_unavailable')
    return result


def mount_stt_compare(app, mode='full'):
    lock = threading.Lock()  # Avoid simultaneous large model loads in this local demo.
    @app.post('/demo/api/stt-compare/run')
    def run(request: STTRequest):
        if mode != 'full':
            return dict(choice=request.choice, model='openai/whisper-tiny/LoRA' if request.choice=='lora' else 'openai/whisper-large-v3-turbo',
                        status='not_run',label='미실행 · smoke 모드',transcript=None,cer=None,input_version=None,audio_sha256=None)
        with lock:
            return transcribe_case(request.choice)

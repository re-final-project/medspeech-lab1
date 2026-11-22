import io
import os
import time
import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel
from .schema import Consultation, grounded

MAX_BYTES=10*1024*1024
MAX_SECONDS=30


class InferenceResponse(BaseModel):
    mode: str
    stt_model: str
    llm_model: str
    transcript: str
    structured: Consultation
    audio_seconds: float
    stt_seconds: float
    structure_seconds: float
    rtf: float
    timing_scope: str
    retained: bool


def create_app(stt=None,llm=None,mode=None,review_backend=None):
    review_backend = review_backend or ('local' if llm is not None else os.getenv('MEDSPEECH_REVIEW_BACKEND','hf'))
    mode=mode or os.getenv("MEDSPEECH_MODE","full")
    app=FastAPI(title="medspeech-lab",description="Synthetic-data research only; no diagnosis or prescription")
    @app.get("/health")
    def health(): return dict(mode=mode,models_loaded=stt is not None and llm is not None,retention=False)

    def ensure_models():
        nonlocal stt,llm
        if stt is None or llm is None:
            if mode=="smoke":
                from .adapters import FixtureSTT,FixtureExtractor
                stt,llm=FixtureSTT(),FixtureExtractor()
            else:
                from pathlib import Path
                import json
                from .adapters import WhisperAdapter,LocalLLM
                root=Path(__file__).resolve().parents[1]
                lock=root/"artifacts/full/model_revisions.json"
                if not lock.exists(): raise HTTPException(503,"Run full setup before serving")
                config=json.loads((root/"configs/full.json").read_text(encoding="utf-8"))
                revisions=json.loads(lock.read_text(encoding="utf-8"))
                stt=WhisperAdapter(config,revisions); llm=LocalLLM(config,revisions)
        return stt,llm

    from .demo import mount_demo
    mount_demo(app,ensure_models,mode,review_backend)
    from .stt_compare import mount_stt_compare
    mount_stt_compare(app,mode)

    @app.post("/infer",response_model=InferenceResponse)
    async def infer(file:UploadFile=File(...)):
        nonlocal stt,llm
        try:
            if file.content_type not in ["audio/wav","audio/x-wav","audio/wave"]:
                raise HTTPException(415,"Only WAV uploads supported")
            blob=await file.read(MAX_BYTES+1)
            if len(blob)>MAX_BYTES: raise HTTPException(413,"File exceeds 10 MiB")
            try:
                info=sf.info(io.BytesIO(blob))
                if info.format!="WAV": raise ValueError("not WAV")
                if info.channels!=1 or info.samplerate!=16000: raise HTTPException(422,"Expected mono 16000 Hz")
                if info.duration<=0 or info.duration>MAX_SECONDS: raise HTTPException(422,"Duration must be (0,30] seconds")
                audio,_=sf.read(io.BytesIO(blob),dtype="float32")
                if not np.isfinite(audio).all(): raise ValueError("nonfinite")
            except HTTPException: raise
            except Exception: raise HTTPException(422,"Unreadable WAV")
            ensure_models()
            start=time.perf_counter(); text=stt.transcribe(audio); stt_s=time.perf_counter()-start
            start=time.perf_counter(); raw=llm.extract(text,"grounded"); llm_s=time.perf_counter()-start
            try: result=Consultation.model_validate_json(raw)
            except Exception: raise HTTPException(502,"Model output failed schema validation")
            if not grounded(result,text): raise HTTPException(502,"Model output lacks exact source evidence")
            return dict(mode=mode,stt_model=stt.name,llm_model=llm.name,transcript=text,structured=result.model_dump(),
                        audio_seconds=info.duration,stt_seconds=stt_s,structure_seconds=llm_s,rtf=stt_s/info.duration,
                        timing_scope="request; first request may include model initialization outside stage timers",retained=False)
        finally: await file.close()
    return app


app=create_app()

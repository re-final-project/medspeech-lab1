import io
import json
import platform
import sys
import os
import time
from pathlib import Path
import importlib.metadata
import numpy as np
import soundfile as sf
from .data import build,qc,dump,load_manifest
from .adapters import FixtureExtractor,FixtureSTT,postprocess,fit_rules
from .metrics import stt_metrics,extraction_metrics,numbers


def environment():
    packages={}
    for name in ["numpy","pydantic","fastapi","pytest","torch","transformers","peft","soundfile"]:
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name]=None
    result=dict(python=sys.version,platform=platform.platform(),processor=platform.processor(),logical_cpus=os.cpu_count(),packages=packages)
    if sys.platform=="win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            result["cpu_model"]=winreg.QueryValueEx(key,"ProcessorNameString")[0].strip()
    try:
        import torch
        result.update(torch_runtime=torch.__version__,quantization_engine=torch.backends.quantized.engine,cuda_available=torch.cuda.is_available(),cuda_device=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,cpu_threads=torch.get_num_threads())
    except ImportError: result["cuda_available"]=False
    return result


def evaluate(root,rows,predictions,out,llm,mode):
    test=[r for r in rows if r["split"]=="test"]; ids=[r["sample_id"] for r in test]
    scores={}; slices={}; extraction={}; examples=[]; cache={}
    for condition,pred in predictions.items():
        texts=[pred[sid] for sid in ids]; scores[condition]=stt_metrics(test,texts); slices[condition]={}
        for key in ["variant","utterance_type"]:
            slices[condition][key]={v:stt_metrics([r for r in test if r[key]==v],[pred[r["sample_id"]] for r in test if r[key]==v]) for v in sorted({r[key] for r in test})}
    dump(Path(out)/"stt_metrics.json",dict(mode=mode,stt=scores,slices=slices,test_ids=ids))
    dump(Path(out)/"stt_predictions.json",predictions)
    inputs={"gold":[r["transcript"] for r in test]}
    inputs.update({k:[v[sid] for sid in ids] for k,v in predictions.items()})
    for source,texts in inputs.items():
        for prompt in ["basic","grounded"]:
            outputs=[]; times=[]; cache_hits=0
            for r,text in zip(test,texts,strict=True):
                key=(prompt,text); hit=mode=="full" and key in cache
                if hit:
                    raw=cache[key]; cache_hits+=1
                else:
                    start=time.perf_counter(); raw=llm.extract(text,prompt); times.append(time.perf_counter()-start)
                    cache[key]=raw
                outputs.append(raw)
                examples.append(dict(sample_id=r["sample_id"],source=source,prompt=prompt,input=text,raw=raw,cache_hit=hit))
                dump(Path(out)/"extraction_predictions.json",examples)
                print(f"Structure {source}/{prompt}: {r['sample_id']} (cache)" if hit else f"Structure {source}/{prompt}: {r['sample_id']} ({times[-1]:.2f}s)",flush=True)
            metrics=extraction_metrics([r["structured_gold"] for r in test],outputs,texts)
            metrics["latency_seconds"]=times; metrics["generation_calls"]=len(times); metrics["cache_hits"]=cache_hits
            extraction[f"{source}/{prompt}"]=metrics
            dump(Path(out)/"extraction_progress.json",extraction)
            dump(Path(out)/"extraction_predictions.json",examples)
    result=dict(mode=mode,performance_claims=mode=="full",stt=scores,slices=slices,extraction=extraction,test_ids=ids,
                rtf_note="See latency.json for real STT timings; fixture timings are not model performance.")
    dump(Path(out)/"metrics.json",result); dump(Path(out)/"extraction_predictions.json",examples)
    dump(Path(out)/"stt_predictions.json",predictions)
    return result


def smoke(base):
    from fastapi.testclient import TestClient
    from .api import create_app
    base=Path(base); root=base/"data/smoke"; out=base/"artifacts/smoke"; out.mkdir(parents=True,exist_ok=True)
    rows=build(root); summary=qc(root,rows)
    from .schema import Consultation
    dump(base/"configs/consultation.schema.json",Consultation.model_json_schema())
    if summary["failures"]: raise RuntimeError("QC failed")
    # Scripted corruption is a metric fixture. C is deliberately absent: no training occurred.
    pred={r["sample_id"]:r["transcript"].replace("38.2","32.8").replace("흉통은 없어요","흉통이 있어요").replace("로수바스타틴","로수 바스타틴") for r in rows}
    # Rule constructed from a train-only injected whitespace error, then frozen.
    dev=[r for r in rows if r["split"] in ["train","validation"]]
    rules=fit_rules(dev,[r["transcript"].replace("타이레놀","타이 레놀") for r in dev])
    dump(out/"postprocess_rules.json",rules)
    b={k:postprocess(v,rules) for k,v in pred.items()}
    result=evaluate(root,rows,{"fixture_A":pred,"fixture_B":b},out,FixtureExtractor(),"smoke")
    with TestClient(create_app(FixtureSTT(),FixtureExtractor(),"smoke")) as client:
        blob=(root/rows[0]["audio_path"]).read_bytes()
        ok=client.post("/infer",files={"file":("fixture.wav",blob,"audio/wav")}); assert ok.status_code==200,ok.text
        bad=client.post("/infer",files={"file":("bad.wav",b"bad","audio/wav")}); assert bad.status_code==422
        dump(out/"api_smoke.json",dict(valid_status=ok.status_code,invalid_status=bad.status_code,response=ok.json()))
    dump(out/"environment.json",environment())
    dump(out/"run_status.json",dict(status="completed",mode="smoke",qc=summary,trained=False,stt="scripted transcript corruption + constant API fixture",llm="rule fixture; prompts share same behavior"))
    return result


def full(base,stage="all"):
    from .adapters import resolve,MMSTTS,WhisperAdapter,LocalLLM
    from .training import train
    base=Path(base); out=base/"artifacts/full"; out.mkdir(parents=True,exist_ok=True)
    dump(out/"run_status.json",dict(status="running",stage=stage))
    config=json.loads((base/"configs/full.json").read_text()); dump(out/"environment.json",environment())
    dump(out/"config.json",config)
    revisions=resolve(config,out/"model_revisions.json")
    root=base/"data/full"
    if stage in ["all","generate"]:
        rows=build(root,MMSTTS(config,revisions)); summary=qc(root,rows)
        if summary["failures"]: raise RuntimeError("QC failed")
        if stage=="generate": return summary
    rows=load_manifest(root)
    if qc(root,rows)["failures"]: raise RuntimeError("QC failed")
    if stage=="structure":
        revisions=resolve(config,out/"model_revisions.json")
        predictions=json.loads((out/"stt_predictions.json").read_text(encoding="utf-8"))
        llm=LocalLLM(config,revisions)
        print(f"LLM loaded: {llm.name}; warming up",flush=True)
        llm.extract(rows[0]["transcript"],"grounded",max_new_tokens=8)
        result=evaluate(root,rows,predictions,out,llm,"full")
        dump(out/"run_status.json",dict(status="completed",stage=stage,llm_warmup=True,llm_quantization=llm.quantization,stt_reused=True))
        return result
    checkpoint=out/"checkpoints/best"
    if stage in ["all","train"]:
        checkpoint=train(root,rows,config,revisions,out/"checkpoints")
        if stage=="train": return dict(checkpoint=str(checkpoint))
    stt=WhisperAdapter(config,revisions); latency=[]
    # Warm up with train audio, never test input.
    warm,_=sf.read(root/rows[0]["audio_path"],dtype="float32"); stt.transcribe(warm)
    def infer(adapter,selection,condition):
        predictions={}
        for r in selection:
            audio,_=sf.read(root/r["audio_path"],dtype="float32"); start=time.perf_counter()
            predictions[r["sample_id"]]=adapter.transcribe(audio); elapsed=time.perf_counter()-start
            latency.append(dict(sample_id=r["sample_id"],condition=condition,seconds=elapsed,audio_seconds=len(audio)/16000,rtf=elapsed/(len(audio)/16000),warmup=True,device=adapter.device))
            print(f"STT {condition}: {r['sample_id']} ({elapsed:.2f}s)",flush=True)
        return predictions
    dev=[r for r in rows if r["split"]!="test"]
    dp=infer(stt,dev,"A_dev"); rules=fit_rules(dev,[dp[r["sample_id"]] for r in dev]); dump(out/"postprocess_rules.json",rules)
    test=[r for r in rows if r["split"]=="test"]; a=infer(stt,test,"A"); b={k:postprocess(v,rules) for k,v in a.items()}
    audit=[dict(sample_id=k,before=a[k],after=b[k],number_changed=numbers(a[k])!=numbers(b[k]),negation_changed=any(a[k].count(t)!=b[k].count(t) for t in ["없","않","아니"])) for k in a if a[k]!=b[k]]
    dump(out/"postprocess_audit.json",audit)
    del stt
    tuned=WhisperAdapter(config,revisions,checkpoint); tuned.transcribe(warm); c=infer(tuned,test,"C"); del tuned
    dump(out/"latency.json",latency)
    dump(out/"stt_predictions.json",{"A":a,"B":b,"C":c})
    dump(out/"stt_metrics.json",{k:stt_metrics(test,[p[r["sample_id"]] for r in test]) for k,p in {"A":a,"B":b,"C":c}.items()})
    llm=LocalLLM(config,revisions); llm.extract(rows[0]["transcript"],"grounded",max_new_tokens=8)
    result=evaluate(root,rows,{"A":a,"B":b,"C":c},out,llm,"full")
    dump(out/"run_status.json",dict(status="completed",stage=stage,llm_warmup=True,llm_quantization=llm.quantization,retention="synthetic offline experiment artifacts only"))
    return result

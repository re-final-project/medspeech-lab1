import json
import re
import time
from pathlib import Path
import numpy as np
import soundfile as sf
from .schema import Consultation

BASIC = "전사에서 명시된 방문 목적, 증상, 부정 증상, 약물, 수치와 단위만 추출하세요. 진단과 처방은 생성하지 마세요. 없는 값은 null 또는 빈 배열입니다. JSON만 반환하세요."
GROUNDED = BASIC + " 먼저 각 값의 연속된 원문 근거를 찾고, 부정 범위를 확인하세요. value와 unit은 원문 그대로 복사하고 evidence에 해당 원문을 붙이세요. 추측하지 마세요."


class FixtureExtractor:
    """Deterministic rule fixture, NOT an LLM or a learned model."""
    name="rule-fixture-not-llm"
    def extract(self,text,prompt="grounded"):
        e=lambda x: dict(value=x,evidence=x)
        result=Consultation().model_dump()
        m=re.search(r"^(.+?) 때문에",text)
        if m: result["purpose"]=e(m[1])
        m=re.search(r"\. (.+?)[이가] 있고 (.+?)(?:은|는) 없어요",text)
        if m:
            result["symptoms"]=[e(m[1])]
            result["denied_symptoms"]=[dict(value=m[2],evidence=m.group(0).split("있고 ")[1])]
        # Independent fixed lexical fixture vocabulary, not manifest lookup.
        for drug in ["타이레놀","암로디핀","메트포르민","오메프라졸","벤토린","씬지로이드","아스피린","세티리진","라식스","이부프로펜","아세트아미노펜","로수바스타틴"]:
            if drug in text: result["medications"].append(e(drug))
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s+(mg/dL|mmHg|mcg|mg|%|도)",text):
            result["measurements"].append(dict(value=m[1],unit=m[2],evidence=m[0]))
        return json.dumps(result,ensure_ascii=False)


class FixtureSTT:
    name="constant-fixture-not-stt"
    def transcribe(self,audio):
        return "테스트 입력입니다."


class WhisperAdapter:
    def __init__(self,config,revisions,checkpoint=None):
        import torch
        from transformers import WhisperProcessor, WhisperForConditionalGeneration
        self.torch=torch; self.config=config; self.name=config["stt"]
        self.processor=WhisperProcessor.from_pretrained(self.name,revision=revisions["stt"],language="Korean",task="transcribe")
        self.model=WhisperForConditionalGeneration.from_pretrained(self.name,revision=revisions["stt"])
        if checkpoint:
            from peft import PeftModel
            self.model=PeftModel.from_pretrained(self.model,checkpoint)
        self.device="cuda" if torch.cuda.is_available() else "cpu"; self.model.to(self.device).eval()
        self.model.generation_config.forced_decoder_ids=None
    def transcribe(self,audio):
        values=self.processor(audio,sampling_rate=16000,return_tensors="pt").input_features.to(self.device)
        with self.torch.inference_mode():
            tokens=self.model.generate(values,language="ko",task="transcribe",num_beams=self.config["num_beams"],do_sample=False,max_new_tokens=self.config["max_new_tokens"])
        return self.processor.batch_decode(tokens,skip_special_tokens=True)[0]


class LocalLLM:
    def __init__(self,config,revisions):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self.torch=torch; self.name=config["llm"]
        self.max_tokens=config.get("llm_max_new_tokens",256)
        self.fail_fast=config.get("llm_fail_fast_json",True)
        self.tokenizer=AutoTokenizer.from_pretrained(self.name,revision=revisions["llm"])
        self.model=AutoModelForCausalLM.from_pretrained(self.name,revision=revisions["llm"]).eval()
        self.device="cuda" if torch.cuda.is_available() else "cpu"; self.model.to(self.device)
        self.quantization="none"
        if self.device=="cpu" and config.get("llm_cpu_int8",False):
            self.model=torch.ao.quantization.quantize_dynamic(self.model,{torch.nn.Linear},dtype=torch.qint8)
            self.quantization="torch-dynamic-int8-linear"
            self.name+="/cpu-dynamic-int8"
    def extract(self,text,prompt="grounded",max_new_tokens=None):
        messages=[dict(role="system",content=(GROUNDED if prompt=="grounded" else BASIC)+"\n"+json.dumps(Consultation.model_json_schema(),ensure_ascii=False)),dict(role="user",content=text)]
        tokens=self.tokenizer.apply_chat_template(messages,add_generation_prompt=True,return_tensors="pt").to(self.device)
        from transformers import StoppingCriteria,StoppingCriteriaList
        from .schema import invalid_json_object_prefix
        tokenizer=self.tokenizer; prefix_length=tokens.shape[1]
        class RejectNonJSON(StoppingCriteria):
            def __call__(self,input_ids,scores,**kwargs):
                return invalid_json_object_prefix(tokenizer.decode(input_ids[0,prefix_length:],skip_special_tokens=True))
        stopping=StoppingCriteriaList([RejectNonJSON()]) if self.fail_fast else StoppingCriteriaList()
        with self.torch.inference_mode():
            out=self.model.generate(tokens,attention_mask=self.torch.ones_like(tokens),do_sample=False,max_new_tokens=max_new_tokens or self.max_tokens,pad_token_id=self.tokenizer.eos_token_id,stopping_criteria=stopping)
        raw=self.tokenizer.decode(out[0,tokens.shape[1]:],skip_special_tokens=True).strip()
        # Preserve raw invalid output for schema pass-rate; no silent repair.
        return raw


class MMSTTS:
    def __init__(self,config,revisions):
        import torch
        from transformers import AutoTokenizer,VitsModel
        self.torch=torch
        self.tokenizer=AutoTokenizer.from_pretrained(config["tts"],revision=revisions["tts"])
        self.model=VitsModel.from_pretrained(config["tts"],revision=revisions["tts"]).eval()
        # Transformers 4.49 constructs Uroman anew for every sentence. Reuse its
        # resource tables, preserving normalization -> romanization -> vocab filter.
        self.romanizer=None
        if self.tokenizer.is_uroman:
            from uroman import Uroman
            self.romanizer=Uroman()
            self.tokenizer.is_uroman=False
    def __call__(self,text):
        from .verbalize import spoken_text
        text=spoken_text(text)
        self.torch.manual_seed(42)
        if self.romanizer:
            text=self.tokenizer._preprocess_char(self.tokenizer.normalize_text(text))
            text=self.romanizer.romanize_string(text)
        with self.torch.inference_mode():
            audio=self.model(**self.tokenizer(text,return_tensors="pt")).waveform[0].numpy()
        rate=self.model.config.sampling_rate
        if rate!=16000: audio=np.interp(np.arange(0,len(audio),rate/16000),np.arange(len(audio)),audio)
        return audio


def resolve(config,path):
    from huggingface_hub import HfApi
    path=Path(path)
    if path.exists(): return json.loads(path.read_text(encoding="utf-8"))
    revisions={k:HfApi().model_info(config[k]).sha for k in ["stt","tts","llm"]}
    from .data import dump
    dump(path,revisions); return revisions


def postprocess(text,rules):
    # No numeric/unit/negation edits permitted. Rules are learned only from train/dev.
    for source,target in rules.items():
        if re.search(r"\d|없|않|아니|mg|ml|mmhg|mcg|%|도",source+target,re.I): continue
        text=text.replace(source,target)
    return text


def fit_rules(rows,predictions):
    rules={}
    for r,h in zip(rows,predictions,strict=True):
        if r["split"] not in ["train","validation"]: raise ValueError("test data forbidden for rule fitting")
        # Conservative whitespace-only term repair observed in dev hypotheses.
        for term in r["key_terms"]:
            pattern=r"\s*".join(map(re.escape,term))
            for m in re.finditer(pattern,h):
                if m[0]!=term: rules[m[0]]=term
    return rules

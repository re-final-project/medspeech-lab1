import copy
import io
import json
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from pydantic import ValidationError
from medspeech.data import build,qc
from medspeech.schema import Consultation,grounded,invalid_json_object_prefix
from medspeech.metrics import distance,stt_metrics,extraction_metrics
from medspeech.adapters import FixtureSTT,FixtureExtractor,fit_rules,postprocess
from medspeech.api import create_app,MAX_BYTES
from medspeech.verbalize import spoken_text


def wav(sr=16000,seconds=1,channels=1):
    buffer=io.BytesIO(); shape=(int(sr*seconds),) if channels==1 else (int(sr*seconds),channels)
    sf.write(buffer,np.zeros(shape),sr,format="WAV"); return buffer.getvalue()


def test_qc_and_split_leak(tmp_path):
    rows=build(tmp_path)
    assert qc(tmp_path,rows)["failures"]==0
    rows[1]["split"]="test"
    assert qc(tmp_path,rows)["failures"]>=2


@pytest.mark.parametrize("defect",["missing","empty","corrupt","rate","gold","duplicate"])
def test_qc_defects(tmp_path,defect):
    rows=build(tmp_path); row=rows[0]; p=tmp_path/row["audio_path"]
    if defect=="missing": p.unlink()
    if defect=="empty": row["transcript"]=" "
    if defect=="corrupt": p.write_bytes(b"broken")
    if defect=="rate": p.write_bytes(wav(8000))
    if defect=="gold": row["structured_gold"]={"diagnosis":"invented"}
    if defect=="duplicate": rows.append(copy.deepcopy(row))
    assert qc(tmp_path,rows)["failures"]>0


def test_cer():
    assert distance("가나다","가라다")==1
    assert distance("abc","")==3
    row=dict(transcript="가나다",key_terms=[],structured_gold={"denied_symptoms":[]})
    assert stt_metrics([row],["가라다"])["cer"]==pytest.approx(1/3)
    assert stt_metrics([row],["가 나 다"])["cer"]==0


def test_tts_numbers_and_units():
    assert spoken_text("SpO2 97 %, 38.2 도, 500 mg, MRI")=="산소 포화도 구십칠 퍼센트, 삼십팔 점 이 도, 오백 밀리그램, 엠알아이"


def test_schema_and_grounding():
    with pytest.raises(ValidationError): Consultation.model_validate({"diagnosis":"감기"})
    with pytest.raises(ValidationError): Consultation.model_validate({"symptoms":[{"value":7,"evidence":"7"}]})
    p=Consultation.model_validate({"symptoms":[{"value":"발열","evidence":"발열"}]})
    assert not grounded(p,"기침이 있어요")
    assert grounded(p,"발열이 있어요")
    metric=extraction_metrics([Consultation().model_dump()],[p.model_dump()],["기침이 있어요"])
    assert metric["schema_pass_rate"]==1 and metric["unsupported_value_rate"]==1


def test_json_prefix_fail_fast():
    assert not invalid_json_object_prefix(' \n {"purpose":')
    assert not invalid_json_object_prefix(' \n ')
    assert invalid_json_object_prefix('설명입니다')
    assert invalid_json_object_prefix('```json')
    assert invalid_json_object_prefix('[{')


def test_no_test_rules():
    with pytest.raises(ValueError): fit_rules([dict(split="test")],[""])
    assert postprocess("38 mg 발열은 없어요",{"38":"83","없어요":"있어요","mg":"ml"})=="38 mg 발열은 없어요"


@pytest.mark.parametrize("body,mime,status",[(b"bad","audio/wav",422),(b"bad","text/plain",415),(wav(8000),"audio/wav",422),(wav(channels=2),"audio/wav",422),(wav(seconds=31),"audio/wav",422),(b"0"*(MAX_BYTES+1),"audio/wav",413)],ids=["corrupt","mime","sample-rate","channels","duration","size"])
def test_api_errors(body,mime,status):
    with TestClient(create_app(FixtureSTT(),FixtureExtractor(),"smoke")) as client:
        assert client.post("/infer",files={"file":("input.wav",body,mime)}).status_code==status


def test_api_success_and_missing():
    with TestClient(create_app(FixtureSTT(),FixtureExtractor(),"smoke")) as client:
        assert client.post("/infer").status_code==422
        response=client.post("/infer",files={"file":("input.wav",wav(),"audio/wav")})
        assert response.status_code==200
        assert response.json()["retained"] is False
        assert response.json()["stt_model"]=="constant-fixture-not-stt"


def test_api_invalid_model():
    class Invalid:
        name="bad"
        def extract(self,*args): return '{"diagnosis":"감기"}'
    with TestClient(create_app(FixtureSTT(),Invalid(),"smoke")) as client:
        assert client.post("/infer",files={"file":("x.wav",wav(),"audio/wav")}).status_code==502


def test_exact_input_cache_keeps_prompts_separate(tmp_path):
    from medspeech.runner import evaluate
    class Counting(FixtureExtractor):
        calls=0
        def extract(self,text,prompt="grounded"):
            self.calls+=1
            return super().extract(text,prompt)
    rows=build(tmp_path/'data'); model=Counting()
    pred={r['sample_id']:r['transcript'] for r in rows if r['split']=='test'}
    result=evaluate(tmp_path/'data',rows,{'A':pred,'B':pred},tmp_path/'out',model,'full')
    assert model.calls==4  # two unique texts, two prompts
    assert result['extraction']['A/basic']['cache_hits']==6
    assert result['extraction']['gold/basic']['generation_calls']==2
    assert result['extraction']['A/basic']['field_f1']==result['extraction']['gold/basic']['field_f1']

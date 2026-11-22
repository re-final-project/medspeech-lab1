import json
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
from medspeech.hf_models import HFQwen, ModelError, validate_symptoms, input_version
from medspeech.api import create_app
from medspeech.comparison import REFERENCE, SIMULATED
from medspeech import hf_models as hf, stt_compare as stt


def output(text):
    return {'headache':{'mention_status':'present','evidence_text':'머리가 계속 아프고'},
            'vomiting':{'mention_status':'absent' if '안' in text else 'present',
                        'evidence_text':'구토는 안 했어요' if '안' in text else '구토를 했어요'}}


CATALOG=[{'id':'Qwen/Qwen3-32B','providers':[{'provider':'deepinfra','status':'live','supports_structured_output':True}]}]


@pytest.mark.parametrize('text,status',[(SIMULATED,'present'),(REFERENCE,'absent')])
def test_provider_schema_and_semantic_expected_values(monkeypatch,text,status):
    monkeypatch.setenv('HF_TOKEN','test-secret-do-not-echo')
    calls=[]
    class Client:
        def chat_completion(self,**kw):
            calls.append(kw);return NS(choices=[NS(message=NS(content=json.dumps(output(text),ensure_ascii=False)))])
    value=HFQwen(lambda **kw:Client(),lambda:CATALOG).analyse(text)
    assert value.headache.mention_status=='present' and value.vomiting.mention_status==status
    assert calls[0]['messages'][1]['content']==text
    assert 'germinoma' not in str(calls) and '송과체' not in str(calls)
    assert calls[0]['response_format']['json_schema']['strict'] is True
    assert set(calls[0]['response_format']['json_schema']['schema']['required'])=={'headache','vomiting'}


@pytest.mark.parametrize('kind,code',[('missing','schema_error'),('extra','schema_error'),('duplicate','schema_error'),('quote','grounding_error'),('null','schema_error'),('polarity','content_error')])
def test_reject_invalid_output(kind,code):
    obj=output(REFERENCE)
    if kind=='missing': del obj['vomiting']
    if kind=='extra':obj['diagnosis']='germinoma'
    if kind=='quote':obj['vomiting']['evidence_text']='구토는 없다고 했어요'
    if kind=='null':obj['vomiting']['evidence_text']=None
    if kind=='polarity':obj['vomiting']['mention_status']='present'
    raw=json.dumps(obj,ensure_ascii=False)
    if kind=='duplicate':raw=raw[:-1]+',"vomiting":'+json.dumps(obj['vomiting'])+'}'
    with pytest.raises(ModelError,match=code):validate_symptoms(raw,REFERENCE)


def test_not_mentioned_evidence_null():
    value=output(SIMULATED);value['vomiting']={'mention_status':'not_mentioned','evidence_text':None}
    assert validate_symptoms(json.dumps(value),'머리가 계속 아프고').vomiting.evidence_text is None
    value['vomiting']['evidence_text']='머리가'
    with pytest.raises(ModelError,match='schema_error'):validate_symptoms(json.dumps(value),'머리가 계속 아프고')


def test_other_symptom_negation_does_not_reverse_headache():
    value=output(REFERENCE);value['headache']['evidence_text']=REFERENCE
    assert validate_symptoms(json.dumps(value),REFERENCE).headache.mention_status=='present'


def test_isolated_sdk_worker_only_receives_transcript_and_safe_environment(monkeypatch):
    monkeypatch.setenv('HF_TOKEN','test-secret')
    monkeypatch.setenv('HF_CLIENT_PYTHON','isolated-python')
    captured=[]
    def run(command,**kwargs):
        captured.append((command,kwargs))
        return NS(returncode=0,stdout=json.dumps({'output':output(REFERENCE)}))
    monkeypatch.setattr(hf.subprocess,'run',run)
    result=HFQwen(catalog=lambda:CATALOG).analyse(REFERENCE)
    assert result.vomiting.mention_status=='absent'
    command,kw=captured[0]
    assert command==['isolated-python','-m','medspeech.hf_worker']
    assert json.loads(kw['input'])=={'text':REFERENCE} and 'test-secret' not in str(command)
    assert 'HF_CLIENT_PYTHON' not in kw['env'] and kw['capture_output']


def test_invalid_worker_response_never_becomes_success(monkeypatch):
    monkeypatch.setenv('HF_TOKEN','test-secret');monkeypatch.setenv('HF_CLIENT_PYTHON','isolated-python')
    monkeypatch.setattr(hf.subprocess,'run',lambda *a,**kw:NS(returncode=0,stdout=json.dumps({'output':output(SIMULATED)})))
    with pytest.raises(ModelError,match='grounding_error'):HFQwen(catalog=lambda:CATALOG).analyse(REFERENCE)


def test_smoke_never_invokes_remote_llm_or_local_stt(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No real model in smoke')
    monkeypatch.setattr(hf.HFQwen,'analyse',forbidden);monkeypatch.setattr(stt,'transcribe_case',forbidden)
    with TestClient(create_app(mode='smoke',review_backend='hf')) as client:
        assert client.post('/demo/api/review/reanalyse',json={'corrected_transcript':REFERENCE}).json()['status']=='unavailable'
        assert client.post('/demo/api/stt-compare/run',json={'choice':'turbo'}).json()['status']=='not_run'


def test_missing_token_and_unsupported_and_call_failure_are_safe(monkeypatch):
    monkeypatch.delenv('HF_TOKEN',raising=False)
    with pytest.raises(ModelError,match='token_missing'):HFQwen(catalog=lambda:[]).analyse(REFERENCE)
    monkeypatch.setenv('HF_TOKEN','secret')
    with pytest.raises(ModelError,match='provider_unsupported'):HFQwen(catalog=lambda:[]).analyse(REFERENCE)
    class Client:
        def chat_completion(self,**kw):raise RuntimeError('secret upstream exception')
    with pytest.raises(ModelError) as error:HFQwen(lambda **kw:Client(),lambda:CATALOG).analyse(REFERENCE)
    assert str(error.value)=='call_failed' and 'secret' not in str(error.value)


def test_review_api_hf_input_versions_and_failure_flags(monkeypatch):
    monkeypatch.delenv('HF_TOKEN',raising=False)
    with TestClient(create_app(mode='full',review_backend='hf')) as client:
        r=client.post('/demo/api/review/reanalyse',json={'corrected_transcript':REFERENCE}).json()
        assert r['error_code']=='token_missing' and r['side']['model_states'] is None and r['schema_valid'] is None
        monkeypatch.setattr(hf.HFQwen,'analyse',lambda self,text:validate_symptoms(json.dumps(output(text)),text))
        for kind,text in [('initial',SIMULATED),('corrected',REFERENCE)]:
            r=client.post('/demo/api/review/reanalyse',json={'corrected_transcript':text,'input_kind':kind}).json()
            assert r['status']=='completed' and r['schema_valid'] is True
            assert r['input_version']==input_version(text,kind) and r['llm_model']=='Qwen/Qwen3-32B'
        def bad(self,text):raise ModelError('grounding_error')
        monkeypatch.setattr(hf.HFQwen,'analyse',bad)
        bad=client.post('/demo/api/review/reanalyse',json={'corrected_transcript':REFERENCE}).json()
        assert bad['status']=='failed' and bad['schema_valid'] is True and bad['symptom_output'] is None


def test_same_audio_and_existing_cer_and_unrun(monkeypatch):
    seen=[]
    class STT:
        name='test-only-adapter'
        def transcribe(self,audio):seen.append(audio.copy());return REFERENCE
    left=stt.transcribe_case('lora',lambda choice:STT());right=stt.transcribe_case('turbo',lambda choice:STT())
    assert (seen[0]==seen[1]).all() and left['audio_sha256']==right['audio_sha256']
    assert left['cer']==right['cer']==0 and left['status']=='completed'
    def fail(choice):raise RuntimeError('unsafe exception')
    failed=stt.transcribe_case('turbo',fail)
    assert failed['transcript'] is failed['cer'] is None and failed['status']=='unavailable'
    with TestClient(create_app(mode='smoke')) as client:
        assert client.post('/demo/api/stt-compare/run',json={'choice':'bad'}).status_code==422

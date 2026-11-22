import json
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from medspeech.api import create_app
from medspeech import comparison as c


def test_fixed_negation_reversal_is_example_not_model_output():
    value = c.build_comparison()
    assert value.label == "모의 전사 오류 · STT 미실행"
    assert value.stt_transcript is None
    assert value.reference.example_answer.headache.status == value.transcript.example_answer.headache.status == "있음"
    assert value.reference.example_answer.vomiting.status == "없음"
    assert value.transcript.example_answer.vomiting.status == "있음"
    assert value.reference.example_answer.vomiting.evidence == "구토는 안 했어요"
    assert value.transcript.example_answer.vomiting.evidence == "구토를 했어요"
    assert value.reference.model_states is value.transcript.model_states is None
    assert ''.join(d.reference for d in value.differences) == c.REFERENCE
    assert ''.join(d.transcript for d in value.differences) == c.SIMULATED
    assert any("안" in d.reference for d in value.differences if d.kind != "equal")


@pytest.mark.parametrize("text,headache,vomiting", [
    (c.REFERENCE,"있음","없음"), (c.SIMULATED,"있음","있음"),
    ("두통은 없어요. 구토는 안 했어요.","없음","없음"),
    ("머리가 계속 아프고", "있음", "언급 없음"),
    ("다리가 아파요.","언급 없음","언급 없음"),
])
def test_bounded_example_annotation(text,headache,vomiting):
    result = c.expected_answer(text)
    assert result.headache.status == headache
    assert result.vomiting.status == vomiting
    for mention in [result.headache,result.vomiting]:
        assert mention.evidence is None or mention.evidence in text


def test_mri_is_independent_of_symptoms_and_hidden_when_off():
    initial = c.build_comparison()
    edited = c.build_comparison("다리가 아파요.","edited")
    assert initial.imaging_findings == edited.imaging_findings
    assert initial.simulated_mri_report == edited.simulated_mri_report
    hidden = c.build_comparison("구토를 했어요.","edited",False)
    assert hidden.imaging_status == "no_information"
    assert hidden.imaging_findings is hidden.simulated_mri_report is None
    assert edited.stt_transcript is None


class STT:
    name="unit-test-stt"
    def transcribe(self,audio): return c.SIMULATED


class LLM:
    name="unit-test-llm"
    def __init__(self,raw='invalid JSON'):
        self.raw=raw; self.inputs=[]
    def extract(self,text,prompt):
        self.inputs.append(text)
        return self.raw


@pytest.fixture
def audio(tmp_path,monkeypatch):
    target=tmp_path/'comparison.wav'
    sf.write(target,np.zeros(1600),16000)
    target.with_suffix('.metadata.json').write_text(json.dumps({'reference_transcript':c.REFERENCE}),encoding='utf-8')
    monkeypatch.setattr(c,'AUDIO_PATH',target)
    return target


def test_actual_stt_kept_even_when_both_json_outputs_fail(audio):
    llm=LLM()
    value=c.run_comparison(lambda:(STT(),llm),'full')
    assert value.stt_status=='completed' and value.stt_transcript==c.SIMULATED
    assert value.source=='actual_stt'
    assert value.reference.structure_status==value.transcript.structure_status=='schema_error'
    assert value.reference.model_states is value.transcript.model_states is None
    assert llm.inputs==[c.REFERENCE,c.SIMULATED]
    assert all('중뇌수도관' not in text and 'germinoma' not in text for text in llm.inputs)


def test_previous_positive_audio_is_not_used_for_negative_reference(audio):
    audio.with_suffix('.metadata.json').write_text(json.dumps({'reference_transcript':'머리가 계속 아프고 구토도 했어요.'}),encoding='utf-8')
    value=c.run_comparison(lambda: (_ for _ in ()).throw(AssertionError()),'full')
    assert value.stt_status=='unavailable' and value.stt_transcript is None


def test_empty_input_does_not_load_models():
    def forbidden(): raise AssertionError('no model call for empty text')
    value=c.compare_edited(c.CompareRequest(transcript='  '),forbidden,'full')
    assert value.transcript.structure_status=='empty_transcript'
    assert value.transcript.example_answer is None
    assert value.transcript.model_states is None
    assert value.stt_transcript is None


def test_empty_actual_stt_is_recorded_without_mock_substitution(audio):
    class Empty(STT):
        def transcribe(self,audio): return ''
    llm=LLM()
    value=c.run_comparison(lambda:(Empty(),llm),'full')
    assert value.stt_transcript=='' and value.source=='actual_stt'
    assert value.transcript.structure_status=='empty_transcript'
    assert not llm.inputs


def test_existing_denied_symptom_schema_maps_to_absent():
    side=c.build_comparison().reference
    llm=LLM(json.dumps({'symptoms':[{'value':'머리가 계속 아프고','evidence':'머리가 계속 아프고'}],
                       'denied_symptoms':[{'value':'구토','evidence':'구토는 안 했어요'}]},ensure_ascii=False))
    c.structure_side(side,llm)
    assert side.structure_status=='completed'
    assert side.model_states.headache.status=='있음'
    assert side.model_states.vomiting.status=='없음'


def test_stored_result_provenance_and_hidden_mri(tmp_path,monkeypatch):
    path=tmp_path/'actual.json'; monkeypatch.setattr(c,'RESULT_PATH',path)
    value=c.build_comparison(c.SIMULATED,'actual_stt',True,'completed')
    path.write_text(value.model_dump_json(),encoding='utf-8')
    stored=c.get_comparison(False)
    assert stored.stored_result and '재실행 안 함' in stored.label
    assert stored.imaging_findings is None
    assert c.get_comparison(allow_stored=False).source=='simulated'
    with TestClient(create_app(mode='smoke')) as client:
        assert client.get('/demo/api/compare').json()['label']=='모의 전사 오류 · STT 미실행'
    assert c.get_comparison(source='simulated').stt_transcript is None
    value.reference.text='unrelated input'
    path.write_text(value.model_dump_json(),encoding='utf-8')
    assert c.get_comparison().source=='simulated'


def test_compare_routes_and_request_validation():
    with TestClient(create_app(mode='smoke')) as client:
        value=client.get('/demo/api/compare?source=simulated&include_mri=false').json()
        assert value['imaging_findings'] is None
        assert value['reference']['example_answer']['vomiting']['status']=='없음'
        assert value['transcript']['example_answer']['vomiting']['status']=='있음'
        assert client.post('/demo/api/compare',json={'transcript':''}).json()['transcript']['structure_status']=='empty_transcript'
        assert client.post('/demo/api/compare',json={'transcript':42}).status_code==422
        assert client.post('/demo/api/compare',json={'transcript':'a'*2001}).status_code==422
        assert client.post('/demo/api/compare',json={'transcript':'a','diagnosis':'invented'}).status_code==422
        assert client.post('/demo/api/compare/run',json={}).json()['stt_transcript'] is None

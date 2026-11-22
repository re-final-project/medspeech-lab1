import json
import pytest
from fastapi.testclient import TestClient
from medspeech.api import create_app
from medspeech import review as r
from medspeech.comparison import REFERENCE, SIMULATED


def forbidden():
    raise AssertionError("No model invocation expected")


def test_mock_session_copies_initial_with_explicit_provenance():
    value=r.review_session('smoke')
    assert value.label=='모의 전사문 · STT 미실행'
    assert value.initial.text==SIMULATED
    assert value.analysis_mode=='example'
    assert value.initial.example_answer.headache.status=='있음'
    assert value.initial.example_answer.vomiting.status=='있음'


@pytest.mark.parametrize('text',[REFERENCE,REFERENCE.rstrip('.'),SIMULATED])
def test_example_is_explicit_and_bounded(text):
    result=r.reanalyse(r.ReviewRequest(corrected_transcript=text,analysis_mode='example'),forbidden,'full')
    assert result.status=='example' and not result.stt_executed
    assert result.side.model_states is None
    assert result.side.example_answer.vomiting.status==('없음' if '안' in text else '있음')
    assert '예시 결과' in result.message


def test_arbitrary_text_never_gets_fabricated_example():
    result=r.reanalyse(r.ReviewRequest(corrected_transcript='다리가 아파요',analysis_mode='example'),forbidden,'smoke')
    assert result.status=='unavailable'
    assert result.side.example_answer is result.side.model_states is None


class STT:
    name='unit-test-stt'
    def transcribe(self,audio):raise AssertionError('STT must not run during review')


class LLM:
    name='unit-test-llm'
    def __init__(self,outputs):self.outputs=iter(outputs);self.inputs=[]
    def extract(self,text,prompt):self.inputs.append(text);return next(self.outputs)


VALID=json.dumps({'symptoms':[{'value':'머리가 계속 아프고','evidence':'머리가 계속 아프고'}],
                  'denied_symptoms':[{'value':'구토','evidence':'구토는 안 했어요'}]},ensure_ascii=False)


def test_only_corrected_input_is_analysed_and_schema_failure_is_retryable():
    llm=LLM(['{"diagnosis":"germinoma"}',VALID])
    with TestClient(create_app(STT(),llm,'full')) as client:
        initial=client.get('/demo/api/review?source=simulated').json()
        body={'corrected_transcript':REFERENCE,'analysis_mode':'model'}
        failed=client.post('/demo/api/review/reanalyse',json=body).json()
        assert failed['status']=='failed' and '재분석 실패' in failed['message']
        assert failed['side']['structure_status']=='schema_error'
        assert failed['side']['example_answer'] is failed['side']['model_states'] is None
        assert llm.inputs==[REFERENCE]
        retried=client.post('/demo/api/review/reanalyse',json=body).json()
        assert retried['status']=='completed' and not retried['stt_executed']
        assert retried['side']['model_states']['vomiting']['status']=='없음'
        assert llm.inputs==[REFERENCE,REFERENCE]
        assert client.get('/demo/api/review?source=simulated').json()==initial


def test_unavailable_model_and_blank_are_not_successful_analyses():
    result=r.reanalyse(r.ReviewRequest(corrected_transcript=REFERENCE),forbidden,'smoke')
    assert result.status=='unavailable' and result.side.example_answer is None
    blank=r.reanalyse(r.ReviewRequest(corrected_transcript='  '),forbidden,'full')
    assert blank.status=='failed' and blank.side.structure_status=='empty_transcript'
    assert blank.side.example_answer is None


def test_mri_is_constant_across_corrections_and_removed_when_hidden():
    positive=r.reanalyse(r.ReviewRequest(corrected_transcript=SIMULATED,analysis_mode='example'),forbidden,'smoke')
    negative=r.reanalyse(r.ReviewRequest(corrected_transcript=REFERENCE,analysis_mode='example'),forbidden,'smoke')
    assert positive.imaging_findings==negative.imaging_findings
    assert positive.simulated_mri_report==negative.simulated_mri_report
    hidden=r.reanalyse(r.ReviewRequest(corrected_transcript=REFERENCE,analysis_mode='example',include_mri=False),forbidden,'smoke')
    assert hidden.imaging_findings is hidden.simulated_mri_report is None


def test_review_api_rejects_empty_and_extra_initial_payloads():
    with TestClient(create_app(mode='smoke')) as client:
        assert client.post('/demo/api/review/reanalyse',json={'corrected_transcript':''}).status_code==422
        assert client.post('/demo/api/review/reanalyse',json={'corrected_transcript':'a'*2001}).status_code==422
        assert client.post('/demo/api/review/reanalyse',json={'corrected_transcript':REFERENCE,'initial_transcript':SIMULATED}).status_code==422

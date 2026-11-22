const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const root = path.resolve(__dirname, '..');
const example = JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/aqueduct_example.json'),'utf8'));
const mock = JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/transcription_comparison.json'),'utf8'));
const html = fs.readFileSync(path.join(root,'medspeech/web/index.html'),'utf8');
const scripts = ['app.js','comparison.js'].map(name => fs.readFileSync(path.join(root,'medspeech/web',name),'utf8'));
const tick = () => new Promise(resolve => setImmediate(resolve));
async function page(edited = mock, run = mock) {
  const dom = new JSDOM(html,{url:'http://localhost/demo/aqueduct',runScripts:'outside-only'});
  const w=dom.window;
  w.structuredClone=structuredClone;
  w.fetch=async (url,options={}) => {
    if (url.includes('/compare')) {
      const value = url.endsWith('/run') ? run : options.method === 'POST' ? edited : mock;
      if (value instanceof Error) throw value;
      return {ok:true,json:async()=>structuredClone(value)};
    }
    return {ok:true,json:async()=>structuredClone(example)};
  };
  scripts.forEach(source => w.eval(source)); await tick();
  return {dom,id:name=>w.document.getElementById(name)};
}

test('fixed example highlights negation change and labels expected answers, not model success',async()=>{
  const {dom,id}=await page();
  assert.equal(id('comparison-status').textContent,'모의 전사 오류 · STT 미실행');
  assert.match(id('comparison-reference-states').textContent,/두통있음/);
  assert.match(id('comparison-reference-states').textContent,/구토없음/);
  assert.match(id('comparison-transcript-states').textContent,/두통있음/);
  assert.match(id('comparison-transcript-states').textContent,/구토있음/);
  assert.match(id('comparison-reference-states').textContent,/구토는 안 했어요/);
  assert.match(id('comparison-transcript-states').textContent,/구토를 했어요/);
  assert.match(id('comparison-reference-states').textContent,/예시 정답/);
  assert.match(id('comparison-reference-states').textContent,/모델 미실행/);
  assert.match([...id('comparison-reference').querySelectorAll('mark')].map(x=>x.textContent).join(''),/안/);
  assert.match([...id('comparison-transcript').querySelectorAll('mark')].map(x=>x.textContent).join(''),/를/);
  dom.window.close();
});

test('MRI toggle clears both JSON views and editing transcripts never changes MRI evidence',async()=>{
  const edited=structuredClone(mock); edited.source='edited'; edited.stt_transcript=null;
  edited.transcript.text='다리가 아파요.';
  edited.transcript.example_answer={headache:{status:'언급 없음',evidence:null},vomiting:{status:'언급 없음',evidence:null}};
  edited.label='직접 수정한 전사문 · STT 미실행';
  const {dom,id}=await page(edited);
  const before=id('imaging-findings').textContent;
  id('comparison-editor').value=edited.transcript.text;
  id('comparison-apply').click(); await tick();
  assert.equal(id('imaging-findings').textContent,before);
  assert.match(id('comparison-transcript-states').textContent,/언급 없음/);
  id('mri-toggle').click();
  assert.equal(id('imaging-findings').textContent,'영상 정보 없음');
  assert.equal(JSON.parse(id('structured-json').textContent).imaging,null);
  assert.equal(JSON.parse(id('comparison-json').textContent).imaging_findings,null);
  assert.equal(JSON.parse(id('comparison-json').textContent).simulated_mri_report,null);
  assert.equal(id('flow-diagram').dataset.state,'blocked');
  assert.match(dom.window.document.querySelector('.diagram-scope').textContent,/가상 시나리오/);
  id('mri-toggle').click();
  assert.equal(id('imaging-findings').textContent,before);
  dom.window.close();
});

test('empty edited transcript is invalid input rather than unmentioned symptoms',async()=>{
  const empty=structuredClone(mock); empty.transcript.text='';
  empty.transcript.example_answer=null; empty.transcript.structure_status='empty_transcript';
  empty.label='빈 전사문 · STT 미실행'; empty.source='edited';
  const {dom,id}=await page(empty);
  id('comparison-editor').value=''; id('comparison-apply').click(); await tick();
  assert.match(id('comparison-transcript').textContent,/빈 전사문/);
  assert.match(id('comparison-transcript-states').textContent,/빈 전사문/);
  assert.doesNotMatch(id('comparison-transcript-states').textContent,/언급 없음/);
  assert.match(id('negation-summary').textContent,/비교 불가/);
  assert.equal(id('comparison-apply').disabled,false);
  dom.window.close();
});

test('actual STT and JSON failures stay distinct from simulated values and example answers',async()=>{
  const actual=structuredClone(mock); actual.source='actual_stt';actual.stt_status='completed';
  actual.stt_transcript=actual.transcript.text; actual.label='실제 STT 전사 결과';
  actual.reference.structure_status=actual.transcript.structure_status='schema_error';
  actual.stt_model='unit-test-stt';actual.llm_model='unit-test-llm';
  const {dom,id}=await page(mock,actual);
  id('comparison-run').click();await tick();
  assert.match(id('comparison-status').textContent,/실제 STT/);
  assert.match(id('comparison-transcript-source').textContent,/실제 STT/);
  assert.match(id('comparison-reference-states').textContent,/JSON 스키마 오류/);
  assert.match(id('comparison-transcript-states').textContent,/예시 정답/);
  assert.doesNotMatch(id('comparison-transcript-states').textContent,/검증 통과/);
  assert.equal(JSON.parse(id('comparison-json').textContent).transcript.model_states,null);
  id('comparison-simulated').click();await tick();
  assert.equal(JSON.parse(id('comparison-json').textContent).stt_transcript,null);
  assert.equal(id('comparison-status').textContent,'모의 전사 오류 · STT 미실행');
  dom.window.close();
});

test('failed comparison request restores controls and does not infer imaging from speech',async()=>{
  const {dom,id}=await page(new Error('연결 실패'));
  const imaging=id('imaging-findings').textContent;
  id('comparison-editor').value='입력'; id('comparison-apply').click();await tick();
  assert.match(id('comparison-status').textContent,/연결 실패/);
  assert.equal(id('comparison-run').disabled,false);
  assert.equal(id('comparison-apply').disabled,false);
  assert.equal(id('imaging-findings').textContent,imaging);
  dom.window.close();
});

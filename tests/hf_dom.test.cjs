const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'..');const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const fixture=JSON.parse(read('tests/fixtures/review_example.json'));
const tick=()=>new Promise(r=>setImmediate(r));
function response(text,kind='corrected',failure=false){return {status:failure?'unavailable':'completed',message:failure?'재분석 실패 · HF_TOKEN 누락':'실제 HF 모델 결과',llm_model:'Qwen/Qwen3-32B',provider:'deepinfra',input_version:kind+':testhash',side:{text,structure_status:failure?'failed':'completed',model_states:failure?null:{headache:{status:'있음',evidence:'머리가 계속 아프고'},vomiting:{status:text.includes('안')?'없음':'있음',evidence:text.includes('안')?'구토는 안 했어요':'구토를 했어요'}}}};}
async function page(fail=false){
 const dom=new JSDOM(read('medspeech/web/index.html'),{url:'http://localhost/demo/aqueduct',runScripts:'outside-only'});const w=dom.window;w.structuredClone=structuredClone;const calls=[];
 w.fetch=async(url,options={})=>{
  const body=options.body?JSON.parse(options.body):null;calls.push({url,body});let value;
  if(url.includes('stt-compare')) value={choice:body.choice,model:body.choice==='lora'?'openai/whisper-tiny/LoRA':'openai/whisper-large-v3-turbo',status:'completed',label:'실제 STT 결과',transcript:body.choice==='lora'?'머리가 계속 아프고 구토를 했어요.':'머리가 계속 아프고 구토는 안 했어요.',cer:.1,input_version:'stt_'+body.choice+':testhash',audio_sha256:'same-audio'};
  else if(url.includes('reanalyse'))value=response(body.corrected_transcript,body.input_kind,fail);
  else if(url.includes('/review'))value={...fixture.session,analysis_mode:'model'};
  else if(url.includes('/compare'))value=JSON.parse(read('tests/fixtures/transcription_comparison.json'));
  else value=JSON.parse(read('tests/fixtures/aqueduct_example.json'));
  return {ok:true,json:async()=>structuredClone(value)};
 };
 for(const name of ['app.js','comparison.js','review.js','stt-options.js'])w.eval(read('medspeech/web/'+name));await tick();
 return {dom,w,id:n=>w.document.getElementById(n),calls};
}
test('initial and corrected inputs use the same route and display distinct input versions and models',async()=>{
 const {dom,id,calls}=await page();const initial=id('review-initial').textContent;
 id('review-initial-analyse').click();await tick();assert.match(id('review-initial-status').textContent,/initial:testhash.*Qwen\/Qwen3-32B/);
 id('review-fill').click();id('review-analyse').click();await tick();assert.match(id('review-result-basis').textContent,/Qwen\/Qwen3-32B/);
 assert.equal(id('review-initial').textContent,initial);assert.equal(calls.filter(c=>c.url.includes('reanalyse'))[0].body.input_kind,'initial');dom.window.close();
});
test('missing token is visible as failure with input/model provenance and retry enabled',async()=>{
 const {dom,id}=await page(true);id('review-analyse').click();await tick();assert.match(id('review-status').textContent,/HF_TOKEN 누락.*Qwen\/Qwen3-32B/);assert.equal(id('review-analyse').disabled,false);assert.doesNotMatch(id('review-corrected-result').textContent,/모의 결과/);dom.window.close();
});
test('LoRA defaults; both STTs retain separate outputs and use same Qwen path without MRI',async()=>{
 const {dom,id,calls}=await page();assert.equal(id('stt-choice').value,'lora');assert.equal(id('stt-turbo-analyse').disabled,true);
 for(const choice of ['lora','turbo']){id('stt-choice').value=choice;id('stt-option-run').click();await tick();id(`stt-${choice}-analyse`).click();await tick();}
 assert.match(id('stt-lora-result').textContent,/LoRA/);assert.match(id('stt-turbo-result').textContent,/whisper-large-v3-turbo/);
 assert.match(id('stt-state-comparison').textContent,/vomiting: LoRA 있음 \/ Turbo 없음/);
 const analyses=calls.filter(c=>c.url.includes('reanalyse'));assert.deepEqual(analyses.map(c=>c.body.input_kind),['stt_lora','stt_turbo']);assert(analyses.every(c=>c.body.include_mri===false));dom.window.close();
});

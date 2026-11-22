"use strict";
(() => {
  const id = name => document.getElementById(name);
  const outputs = {}, analyses = {};
  let busy = false;
  function compare() {
    const left = analyses.lora, right = analyses.turbo;
    id('stt-state-comparison').textContent = left?.status === 'completed' && right?.status === 'completed'
      ? ['headache','vomiting'].map(k => `${k}: LoRA ${left.side.model_states[k].status} / Turbo ${right.side.model_states[k].status}`).join(' · ')
      : '두 STT 전사의 Qwen 분석이 모두 성공하면 증상 상태를 비교합니다.';
  }
  function controls() {
    id('stt-option-run').disabled = busy;
    for (const k of ['lora','turbo']) id(`stt-${k}-analyse`).disabled = busy || outputs[k]?.status !== 'completed';
  }
  id('stt-option-run').addEventListener('click',async()=>{
    if(busy)return;busy=true;controls();
    const choice=id('stt-choice').value;
    id('stt-options-status').textContent='STT 실행 중 · 첫 실행은 모델 로딩이 포함됩니다.';
    try {
      const r=await fetch('/demo/api/stt-compare/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({choice})});
      if(!r.ok)throw new Error('STT 요청 실패');
      const value=await r.json();outputs[choice]=value;delete analyses[choice];
      id(`stt-${choice}-structure`).textContent='Qwen 분석 미실행';
      id(`stt-${choice}-result`).textContent=`${value.model} · ${value.label}\n${value.transcript || '미실행'}\nCER: ${value.cer == null ? '미측정' : (value.cer*100).toFixed(2)+'%'}\n입력 버전: ${value.input_version || '없음'}\n음성 SHA256: ${value.audio_sha256 || '없음'}`;
      id('stt-options-status').textContent=value.label;compare();
    }catch(_){id('stt-options-status').textContent='STT 호출 실패 · 재시도할 수 있습니다.';}
    busy=false;controls();
  });
  for(const choice of ['lora','turbo']) id(`stt-${choice}-analyse`).addEventListener('click',async()=>{
    if(busy || outputs[choice]?.status!=='completed')return;busy=true;controls();
    const node=id(`stt-${choice}-structure`);node.textContent='Qwen 분석 중';
    try {
      const r=await fetch('/demo/api/review/reanalyse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({corrected_transcript:outputs[choice].transcript,analysis_mode:'model',input_kind:'stt_'+choice,include_mri:false})});
      if(!r.ok)throw new Error('분석 요청 실패');
      const v=await r.json();analyses[choice]=v;
      node.textContent=`${v.message}\n모델: ${v.llm_model || '미실행'} / ${v.provider || ''}\n입력 버전: ${v.input_version}\n`+(v.status==='completed'?['headache','vomiting'].map(k=>`${k}: ${v.side.model_states[k].status} · 근거: ${v.side.model_states[k].evidence || '없음'}`).join('\n'):'');
      compare();
    }catch(_){delete analyses[choice];node.textContent='구조화 호출 실패 · 재시도할 수 있습니다.';compare();}
    busy=false;controls();
  });
})();

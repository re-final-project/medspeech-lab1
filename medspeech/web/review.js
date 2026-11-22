"use strict";
(() => {
  const id = name => document.getElementById(name);
  let session = null, latest = null, failure = null, busy = false;
  const negativeExample = "머리가 계속 아프고 구토는 안 했어요.";
  const visibleMRI = () => id("mri-toggle").getAttribute("aria-expanded") === "true";
  const stale = () => !!latest && (latest.side.text !== id("review-editor").value || !!failure);
  function resultStates(side, exampleAllowed) {
    return side.model_states || (exampleAllowed ? side.example_answer : null);
  }
  function showStates(node, side, exampleAllowed) {
    node.replaceChildren();
    const values = resultStates(side, exampleAllowed);
    const label = document.createElement("p"); label.className = "state-source";
    label.textContent = side.model_states ? "실제 모델 결과" : values ? "예시 결과 · 모델 미실행" : `모델 결과 없음 · ${side.structure_status}`;
    node.append(label);
    if (values) for (const [key,name] of [["headache","두통"],["vomiting","구토"]]) {
      const row = document.createElement("div"); row.className="review-mention";
      const title=document.createElement("strong");title.textContent=`${name}: ${values[key].status}`;
      const proof=document.createElement("p");proof.textContent=values[key].evidence ? `근거: ${values[key].evidence}` : "근거 없음 · 언급 없음";
      row.append(title,proof);node.append(row);
    }
  }
  function render() {
    if (!session) return;
    const draft=id("review-editor").value;
    const isStale=stale();
    id("review-source").textContent=session.label;
    id("review-reference").textContent=session.reference_transcript;
    id("review-initial").textContent=session.initial.text;
    showStates(id("review-initial-result"),session.initial,session.analysis_mode === "example");
    const basis=id("review-result-basis");basis.classList.toggle("stale-result",isStale);
    basis.textContent=latest ? (isStale ? "이전 수정문 기준" : "현재 수정문 기준")+` · 분석 입력: ${latest.side.text}` : "수정문 재분석 전";
    if (latest) showStates(id("review-corrected-result"),latest.side,latest.status === "example");
    else {id("review-corrected-result").textContent="유효한 수정문 분석 결과 없음";}
    const status=id("review-status");
    status.textContent=busy ? "수정문 재분석 중 · 초기 전사와 기존 결과는 유지됩니다." : failure ? failure.message : !draft.trim() ? "빈 수정문 · 재분석할 수 없습니다." : isStale ? "수정문이 변경되었습니다 · 이전 수정문 기준 결과입니다." : latest ? latest.message : "초기 전사문을 복사했습니다. 검토 후 수정문 재분석을 실행하세요.";
    status.classList.toggle("error",!!failure);
    status.classList.toggle("running",busy);
    id("review-analyse").disabled=busy || !draft.trim();
    id("review-demo").disabled=busy;id("review-fill").disabled=busy;
    const transitions=id("review-transitions");transitions.replaceChildren();
    const before=resultStates(session.initial,session.analysis_mode === "example");
    const after=latest ? resultStates(latest.side,latest.status === "example") : null;
    for (const [key,name] of [["headache","두통"],["vomiting","구토"]]) {
      const row=document.createElement("div");row.className="review-transition";row.dataset.symptom=key;
      const changed=!!before && !!after && before[key].status !== after[key].status;
      row.classList.toggle("changed",changed);
      const title=document.createElement("strong");
      title.textContent=`${name}: ${before ? before[key].status : "초기 결과 없음"} → ${after ? after[key].status : "수정 결과 없음"}${changed ? " · 상태 변경" : before && after ? " · 상태 동일" : ""}`;
      const proof=document.createElement("p");proof.className="evidence";
      proof.textContent=`초기 근거: ${before?.[key].evidence || "없음"} / 수정 근거: ${after?.[key].evidence || "없음"}`;
      row.append(title,proof);transitions.append(row);
    }
    const copy=structuredClone({initial_snapshot:session,last_analysis:latest,last_failed_attempt:failure,draft,previous_draft_basis:isStale});
    if (!visibleMRI()) for (const value of [copy.initial_snapshot,copy.last_analysis,copy.last_failed_attempt]) if(value){value.simulated_mri_report=null;value.imaging_findings=null;}
    id("review-json").textContent=JSON.stringify(copy,null,2);
  }
  async function load(source="auto") {
    if(busy)return;
    try {
      const response=await fetch(`/demo/api/review?source=${source}`);
      if(!response.ok)throw new Error(`검토 시작 실패 (HTTP ${response.status})`);
      session=structuredClone(await response.json());latest=null;failure=null;
      id("review-editor").value=session.initial.text;render();
    }catch(error){id("review-status").textContent=error.message;id("review-status").classList.add("error");}
  }
  id("review-editor").addEventListener("input",render);
  id("review-fill").addEventListener("click",()=>{id("review-editor").value=negativeExample;render();});
  id("review-demo").addEventListener("click",()=>load("simulated"));
  id("mri-toggle").addEventListener("click",render);
  id("review-analyse").addEventListener("click",async()=>{
    if(busy || !session || !id("review-editor").value.trim())return;
    const submitted=id("review-editor").value;
    busy=true;failure=null;render();
    try {
      const response=await fetch("/demo/api/review/reanalyse",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({corrected_transcript:submitted,analysis_mode:session.analysis_mode,include_mri:true})});
      if(!response.ok)throw new Error(`재분석 실패 (HTTP ${response.status})`);
      const value=await response.json();
      if(value.side?.text !== submitted)throw new Error("재분석 실패 · 응답의 입력 기준이 일치하지 않습니다.");
      if(value.status === "completed" || value.status === "example") latest=value;
      else failure=value;
    }catch(error){failure={status:"failed",message:`재분석 실패 · ${error.message} · 재시도할 수 있습니다.`,side:{text:submitted}};}
    busy=false;render();
  });
  load();
})();

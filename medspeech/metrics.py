import re
import unicodedata
from collections import Counter
from .schema import Consultation, items


def normalize(text):
    # Preserve decimal points, slashes, percent, negation and case-normalized abbreviations.
    return " ".join(re.sub(r"[^\w\s.%/]", " ", unicodedata.normalize("NFKC", text).lower()).split())


def distance(a,b):
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        curr=[i]
        for j,y in enumerate(b,1): curr.append(min(curr[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
        prev=curr
    return prev[-1]


def f1(gold,pred):
    g,p=Counter(gold),Counter(pred); tp=sum((g&p).values())
    return dict(tp=tp,fp=sum(p.values())-tp,fn=sum(g.values())-tp)


def score_counts(c):
    return 2*c["tp"]/max(2*c["tp"]+c["fp"]+c["fn"],1)


def numbers(text):
    return re.findall(r"(?<![\w.])\d+(?:\.\d+)?\s*(?:mg/dl|mmhg|mcg|mg|ml|%|도)?",normalize(text))


def stt_metrics(rows,preds):
    ce=cn=we=wn=0; term=dict(tp=0,fp=0,fn=0); num=neg=0
    vocabulary=sorted({t for r in rows for t in r["key_terms"]})
    for r,p in zip(rows,preds,strict=True):
        g=normalize(r["transcript"]); h=normalize(p)
        gc=g.replace(" ",""); hc=h.replace(" ","")
        ce+=distance(gc,hc); cn+=len(gc); we+=distance(g.split(),h.split()); wn+=len(g.split())
        counts=f1([t for t in vocabulary if normalize(t) in g],[t for t in vocabulary if normalize(t) in h])
        for k in term: term[k]+=counts[k]
        num+=Counter(numbers(g))==Counter(numbers(h))
        # Exact denied evidence avoids scoring positive mention as negation success.
        neg+=all(normalize(v["evidence"]) in h for v in r["structured_gold"]["denied_symptoms"])
    n=len(rows)
    return dict(n=n,cer=ce/max(cn,1),wer=we/max(wn,1),medical_term_f1=score_counts(term),
                number_unit_exact=num/max(n,1),negation_exact=neg/max(n,1),char_edits=ce,reference_chars=cn)


def extraction_metrics(golds,outputs,texts):
    valid=0; evidence_ok=0; hallucinated=0; count=0
    fields={k:dict(tp=0,fp=0,fn=0) for k in Consultation.model_fields}; errors=[]
    for i,(g,out,text) in enumerate(zip(golds,outputs,texts,strict=True)):
        try: p=Consultation.model_validate_json(out) if isinstance(out,str) else Consultation.model_validate(out); valid+=1
        except Exception as e:
            p=Consultation(); errors.append(dict(index=i,type="schema",detail=str(e)[:250]))
        gold=Consultation.model_validate(g)
        for field in fields:
            def keys(obj):
                return [(x.value,getattr(x,"unit",None)) for k,x in items(obj) if k==field]
            c=f1(keys(gold),keys(p))
            for k in c: fields[field][k]+=c[k]
        for _,x in items(p):
            count+=1
            evidence_ok+=x.evidence in text and x.value in x.evidence and (getattr(x,"unit",None) is None or x.unit in x.evidence)
            hallucinated+=x.value not in text or (getattr(x,"unit",None) is not None and x.unit not in text)
        if p.model_dump()!=gold.model_dump(): errors.append(dict(index=i,type="content",prediction=p.model_dump(),gold=g))
    return dict(n=len(golds),schema_pass_rate=valid/max(len(golds),1),field_f1={k:score_counts(v) for k,v in fields.items()},
                field_counts=fields,evidence_match_rate=evidence_ok/max(count,1),unsupported_value_rate=hallucinated/max(count,1),
                extracted_items=count,errors=errors)

"""Reproducible real calls; no token or upstream exception is serialized."""
import argparse
import json
import platform
import os
from pathlib import Path
from .comparison import REFERENCE, SIMULATED
from .data import dump
from .review import ReviewRequest, reanalyse


def main():
    import sys
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--stt',choices=['none','lora','turbo','both'],default='none')
    parser.add_argument('--output',type=Path,default=Path('artifacts/hf/verification.json'))
    args=parser.parse_args()
    report={'hardware':platform.platform(),'qwen':[],'stt':[],'stt_extraction':[]}
    for text,expected in [(SIMULATED,'present'),(REFERENCE,'absent')]:
        value=reanalyse(ReviewRequest(corrected_transcript=text),lambda:None,'full','hf')
        out=value.symptom_output
        correct=(out['headache']['mention_status']=='present' and out['vomiting']['mention_status']==expected) if out else None
        report['qwen'].append({'analysis':value.model_dump(),'symptom_states_correct':correct,
                               'verification':'verified' if out else 'unverified'})
    if args.stt!='none':
        import torch
        report['hardware']={'platform':platform.platform(),'torch':torch.__version__,
                            'processor':platform.processor(),'logical_cpus':os.cpu_count(),'torch_threads':torch.get_num_threads(),
                            'device':torch.cuda.get_device_name() if torch.cuda.is_available() else 'cpu',
                            'warmup':False,'timing':'STT generation excludes model loading; no warmup'}
        from .stt_compare import transcribe_case
        for choice in (['lora','turbo'] if args.stt=='both' else [args.stt]):
            value=transcribe_case(choice);report['stt'].append(value)
            if value['status']=='completed':
                analysis=reanalyse(ReviewRequest(corrected_transcript=value['transcript'],input_kind='stt_'+choice),lambda:None,'full','hf')
                report['stt_extraction'].append(analysis.model_dump())
            dump(args.output,report)  # Partial evidence survives a later model load failure.
    dump(args.output,report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()

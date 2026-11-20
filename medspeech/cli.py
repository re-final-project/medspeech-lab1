import argparse
import json
import traceback
from pathlib import Path
from .data import qc,dump


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["smoke","full","qc","report"])
    parser.add_argument("--stage",default="all",choices=["all","generate","train","evaluate","structure"])
    parser.add_argument("--base",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--data",type=Path)
    args=parser.parse_args()
    from .runner import smoke,full,environment
    from .reporting import report
    try:
        if args.command=="report":
            report(args.base); result={"report":"reports/experiment_report.md"}
        else:
            result=smoke(args.base) if args.command=="smoke" else full(args.base,args.stage) if args.command=="full" else qc(args.data or args.base/"data/smoke")
        stale=args.base/f"artifacts/{args.command}/failure.json"
        if stale.exists(): stale.unlink()
        if (args.base/"artifacts/smoke/metrics.json").exists(): report(args.base)
        display=result
        if isinstance(result,dict) and "stt" in result:
            display=dict(mode=result["mode"],stt=result["stt"],metrics_path=f"artifacts/{args.command}/metrics.json")
        print(json.dumps(display,ensure_ascii=False,indent=2))
    except Exception as e:
        dump(args.base/f"artifacts/{args.command}/failure.json",dict(error=repr(e),traceback=traceback.format_exc(),environment=environment(),stage=args.stage))
        if (args.base/"artifacts/smoke/metrics.json").exists(): report(args.base)
        raise


if __name__=="__main__": main()

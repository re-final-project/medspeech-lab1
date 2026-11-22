"""Private stdin/stdout bridge for an isolated HF SDK environment."""
import json
import sys
from .hf_models import HFQwen, ModelError


def main():
    if hasattr(sys.stdin,'reconfigure'): sys.stdin.reconfigure(encoding='utf-8')
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try:
        payload=json.loads(sys.stdin.read())
        text=payload['text']
        if not isinstance(text,str) or not text.strip() or len(text)>2000:
            raise ModelError('schema_error')
        value=HFQwen().analyse(text)
        print(json.dumps({'output':value.model_dump()},ensure_ascii=False))
    except ModelError as error:
        print(json.dumps({'error_code':error.code}))
    except Exception:
        print(json.dumps({'error_code':'call_failed'}))


if __name__=='__main__':main()

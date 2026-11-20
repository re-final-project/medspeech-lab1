"""Optional HF copy-cache fallback for managed Windows without symlink probes.

Run from the project root with the full environment:
  .\.venv\Scripts\python.exe tools\run_windows_copy_cache.py full
"""
import os
from pathlib import Path
import sys

project=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project))
os.environ.setdefault("HF_HOME",str(project/".cache/huggingface"))
os.environ.setdefault("OMP_NUM_THREADS","2")
os.environ.setdefault("MKL_NUM_THREADS","2")
import huggingface_hub.file_download as download
download.are_symlinks_supported=lambda cache_dir=None:False
from medspeech.cli import main
main()

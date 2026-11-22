"""Optional managed-Windows copy-cache wrapper for transcript review."""
import os
import sys
from pathlib import Path
project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project))
os.environ.setdefault("HF_HOME", str(project/".cache/huggingface"))
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
import huggingface_hub.file_download as download
download.are_symlinks_supported = lambda cache_dir=None: False
from medspeech.review import main
main()

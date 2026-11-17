import importlib.util
from pathlib import Path


def load_setup_sheet():
    p = Path(__file__).resolve().parent.parent / "scripts" / "setup_sheet.py"
    spec = importlib.util.spec_from_file_location("setup_sheet", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

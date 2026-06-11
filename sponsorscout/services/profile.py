import json
from pathlib import Path
DEFAULT_PROFILE = json.loads((Path(__file__).resolve().parent.parent / "data" / "default_profile.json").read_text(encoding="utf-8"))

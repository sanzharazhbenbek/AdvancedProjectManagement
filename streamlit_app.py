from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


app_path = Path(__file__).with_name("app.py")
spec = spec_from_file_location("eventsphere_root_app", app_path)
module = module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
module.main()

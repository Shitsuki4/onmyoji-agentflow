"""Source pins for the OAS success/finish scheduling branch (GPL-3.0)."""
import hashlib

from ..workflow.oas_schedule import PARAMS


PINS = {
    "tasks/base_task.py": "6d8849bcfdb368a012b9e19e37d446ed3022dad39974ab6eb237c959c43b4c20",
    "module/config/config.py": "938cd30134f8113f63fba7bd68f419b666ccce188789e09be6ea36b6efc46978",
    "module/config/utils.py": "722a5ce41fef7e72320dcb03a91b6db61d9fcea91d5add30b194b58ff4753bb8",
    "tasks/Component/config_scheduler.py": "5b05654dce98f0bb5cf7a0237ea8c876be8407fbbb5a7ef082a371999dd7d0d5",
}


def bind_schedule(source, raw):
    for path, pin in PINS.items():
        content = (source / path).read_text(encoding="utf-8-sig").encode("utf-8")
        if hashlib.sha256(content).hexdigest() != pin:
            raise ValueError(f"OAS scheduling source fingerprint mismatch: {path}")
    raw["params"].update({name: dict(spec) for name, spec in PARAMS.items()})

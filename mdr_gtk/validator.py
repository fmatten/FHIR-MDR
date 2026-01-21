from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ValidatorResult:
    ok: bool
    message: str
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def run_external_validator(file_path: str, *, mode: str = "xml") -> Optional[ValidatorResult]:
    """Run an external FHIR validator if configured.

    Configuration:
      - Set env var `FHIR_VALIDATOR_TEMPLATE` to a shell-like command template that includes `{file}`.
        Example:
          export FHIR_VALIDATOR_TEMPLATE='java -jar /opt/validator/validator_cli.jar {file} -version 4.0.1'

    If not configured, returns None (caller should skip).
    """
    tpl = os.environ.get("FHIR_VALIDATOR_TEMPLATE")
    if not tpl:
        return None

    cmd = tpl.format(file=shlex.quote(str(Path(file_path).resolve())))
    # Execute via shell to allow user-provided quoting/args
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    ok = (p.returncode == 0)
    msg = "Validator OK" if ok else f"Validator failed (rc={p.returncode})"
    return ValidatorResult(ok=ok, message=msg, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)

import base64
import subprocess

from app.core.logging import get_logger

logger = get_logger(__name__)

CONTAINER = "ledger-sandbox"
EXEC_TIMEOUT = 30


def run(code: str) -> str:
    """Run matplotlib code inside the sandbox container. Returns base64-encoded PNG.

    Raises RuntimeError if the code errors out or times out.
    """
    wrapped = f"""
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import json

{code}

plt.savefig(sys.stdout.buffer, format='png', bbox_inches='tight', dpi=150)
plt.close('all')
"""

    try:
        result = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "python", "-c", wrapped],
            capture_output=True,
            timeout=EXEC_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Sandbox timeout after %ss", EXEC_TIMEOUT)
        raise RuntimeError(f"Chart generation timed out after {EXEC_TIMEOUT}s.")

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")[:500]
        logger.warning("Sandbox error: %s", stderr)
        raise RuntimeError(f"Sandbox failed: {stderr}")

    return base64.b64encode(result.stdout).decode()
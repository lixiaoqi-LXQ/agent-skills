#!/usr/bin/env python3
"""Install only missing Plannotator dependencies, outside the user's project."""
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

from review import binary, code_cli, extension_present


def main():
    code = code_cli()
    if not code:
        raise SystemExit('VS Code CLI not found. Open a VS Code integrated terminal or set PLANNOTATOR_CODE_CLI.')
    if not binary():
        if os.name != 'posix':
            raise SystemExit('Use this installer from Linux, WSL, or macOS.')
        with tempfile.TemporaryDirectory(prefix='plannotator-install-') as tmp:
            script = Path(tmp) / 'install.sh'
            with urllib.request.urlopen('https://plannotator.ai/install.sh', timeout=30) as response:
                script.write_bytes(response.read())
            env = os.environ.copy()
            env.pop('USERPROFILE', None)
            subprocess.run(['bash', str(script), '--minimal', '--non-interactive'], env=env, check=True)
    if not extension_present(code):
        subprocess.run([code, '--install-extension', 'backnotprop.plannotator-webview'], check=True)
    if not binary() or not extension_present(code):
        raise SystemExit('Dependency verification failed; inspect the installation output.')
    print('Plannotator CLI and VS Code extension are ready.')


if __name__ == '__main__':
    main()

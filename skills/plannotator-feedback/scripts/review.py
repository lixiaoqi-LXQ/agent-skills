#!/usr/bin/env python3
"""Private Plannotator feedback sessions routed only through VS Code. Stdlib only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from quiet_ui import launch as launch_quiet_ui

EXTENSION = 'backnotprop.plannotator-webview'
SCHEMA = 'plannotator-feedback/1'


def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.write-', delete=False) as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        tmp = Path(f.name)
    os.replace(tmp, path)


def binary():
    candidate = shutil.which('plannotator')
    local = Path.home() / '.local/bin/plannotator'
    return candidate or (str(local) if os.access(local, os.X_OK) else None)


def code_cli():
    return shutil.which(os.environ.get('PLANNOTATOR_CODE_CLI', 'code'))


def extension_present(code):
    if not code:
        return False
    result = subprocess.run([code, '--list-extensions'], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('VS Code extension listing failed: ' + result.stderr.strip())
    return EXTENSION in result.stdout.lower().splitlines()


def registry_path():
    if os.environ.get('PLANNOTATOR_VSCODE_REGISTRY'):
        return Path(os.environ['PLANNOTATOR_VSCODE_REGISTRY']).expanduser().resolve()
    if os.environ.get('PLANNOTATOR_DATA_DIR'):
        return Path(os.environ['PLANNOTATOR_DATA_DIR']).expanduser().resolve() / 'vscode-ipc.json'
    legacy = Path.home() / '.plannotator'
    xdg = os.environ.get('XDG_DATA_HOME', '')
    if not legacy.exists() and xdg and Path(xdg).is_absolute():
        return Path(xdg) / 'plannotator/vscode-ipc.json'
    return legacy / 'vscode-ipc.json'


def registry():
    try:
        value = json.loads(registry_path().read_text())
        return {str(Path(k).resolve()): int(v) for k, v in value.items() if k and 0 < int(v) < 65536}
    except FileNotFoundError:
        return {}


def ipc_alive(port):
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{int(port)}/', timeout=1).close()
    except urllib.error.HTTPError as e:
        return e.code == 404 and e.read() == b'not found'
    except (OSError, ValueError):
        return False
    return False


def select_workspace(target, explicit=None):
    entries = registry()
    if explicit:
        selected = str(Path(explicit).expanduser().resolve())
    else:
        inherited = os.environ.get('PLANNOTATOR_VSCODE_PORT')
        for workspace, port in entries.items():
            if inherited == str(port) and ipc_alive(port):
                return workspace, port
        matches = [p for p in entries if target == Path(p) or Path(p) in target.parents]
        selected = max(matches, key=len) if matches else str(target if target.is_dir() else target.parent)
    if not Path(selected).is_dir():
        raise RuntimeError('VS Code workspace directory does not exist: ' + selected)
    port = entries.get(selected)
    if port and ipc_alive(port):
        return selected, port
    code = code_cli()
    if not code:
        raise RuntimeError('VS Code CLI is missing; see references/installation.md.')
    subprocess.run([code, '--new-window', selected], check=True, capture_output=True, text=True, timeout=15)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        port = registry().get(selected)
        if port and ipc_alive(port):
            return selected, port
        time.sleep(.4)
    raise RuntimeError('VS Code extension did not register workspace ' + selected + '; activate it or reload that window.')


def open_panel(port, url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Expected a local Plannotator URL.')
    query = urllib.parse.urlencode({'url': url})
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/open?{query}', timeout=10) as response:
        if response.status != 200 or response.read() != b'ok':
            raise RuntimeError('VS Code did not accept the review URL.')


def process_identity(pid):
    """Return an identity that changes when an OS pid is reused."""
    try:
        if sys.platform.startswith('linux'):
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            return None if fields[0] == 'Z' else fields[19]
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart='], capture_output=True, text=True)
        return result.stdout.strip() or None
    except (OSError, IndexError):
        return None


def load_session(value):
    directory = Path(value).expanduser().resolve()
    data = json.loads((directory / 'session.json').read_text())
    if data.get('schema') != SCHEMA or data.get('session_dir') != str(directory):
        raise RuntimeError('Not a session created by this skill.')
    return directory, data


def running(data):
    return bool(data.get('pid_identity')) and process_identity(data['pid']) == data['pid_identity']


def result_for(directory, data):
    feedback = directory / 'feedback.json'
    try:
        result = json.loads(feedback.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        result = None
    if isinstance(result, dict) and result.get('decision') in ('annotated', 'approved', 'dismissed'):
        return {'status': 'completed', 'session_dir': str(directory), 'handled': (directory / 'handled.json').exists(), 'result': result}
    if running(data):
        return {'status': 'waiting', 'session_dir': str(directory), 'url': data.get('url')}
    failure = directory / 'failure.json'
    if failure.exists():
        return {'status': 'failed', 'session_dir': str(directory), **json.loads(failure.read_text())}
    if (directory / 'cancelled.json').exists():
        return {'status': 'cancelled', 'session_dir': str(directory)}
    return {'status': 'failed', 'session_dir': str(directory), 'error': 'Service ended without a valid decision. Inspect server.log and feedback.json; do not treat this as approval.'}


def cancel(directory, data):
    if not running(data):
        return result_for(directory, data)
    write_json(directory / 'cancelled.json', {'at': now()})
    os.kill(data['pid'], signal.SIGTERM)
    return {'status': 'cancelled', 'session_dir': str(directory)}


def build_command(args, target):
    executable = binary()
    if not executable:
        raise RuntimeError('Plannotator CLI is missing; see references/installation.md.')
    if args.command == 'document':
        return [executable, 'annotate', str(target), '--json'], target if target.is_dir() else target.parent
    if not target.is_dir():
        raise RuntimeError('Changes mode requires a repository directory.')
    cmd = [executable, 'review', '--json', '--no-git-remote-check']
    if args.patch_file:
        if args.base or args.diff_type:
            raise RuntimeError('--patch-file cannot be combined with --base or --diff-type.')
        patch = Path(args.patch_file).expanduser().resolve(strict=True)
        cmd += ['--patch-file', str(patch)]
    else:
        cmd += [str(target), '--diff-type', args.diff_type or ('since-base' if args.base else 'uncommitted')]
        if args.base:
            cmd += ['--base', args.base]
    return cmd, target


def start(args):
    target = Path(args.target).expanduser().resolve(strict=True)
    cmd, cwd = build_command(args, target)
    workspace, port = select_workspace(target, args.workspace)
    directory = Path(tempfile.mkdtemp(prefix='plannotator-review-'))
    (directory / 'data').mkdir(mode=0o700)
    env = os.environ.copy()
    env.update(PLANNOTATOR_DATA_DIR=str(directory / 'data'), PLANNOTATOR_BROWSER='none', PLANNOTATOR_REMOTE='0', PLANNOTATOR_ORIGIN='codex' if os.environ.get('CODEX_THREAD_ID') else env.get('PLANNOTATOR_ORIGIN', ''))
    env.pop('PLANNOTATOR_PORT', None)
    data = {'schema': SCHEMA, 'session_dir': str(directory), 'created_at': now(), 'target': str(target), 'mode': args.command, 'command': cmd, 'cwd': str(cwd), 'workspace': workspace, 'ipc_port': port, 'owner': args.owner or os.environ.get('CODEX_THREAD_ID') or os.environ.get('HERDR_PANE_ID') or 'caller', 'pid': None, 'pid_identity': None}
    write_json(directory / 'session.json', data)
    emit({'status': 'starting', 'session_dir': str(directory), 'target': str(target), 'workspace': workspace})
    proc = None
    try:
        with (directory / 'feedback.json').open('w') as out, (directory / 'server.log').open('w') as err:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            data.update(pid=proc.pid, pid_identity=process_identity(proc.pid))
            write_json(directory / 'session.json', data)
            deadline = time.monotonic() + 45
            while proc.poll() is None:
                log = (directory / 'server.log').read_text(errors='replace')
                match = re.search(r'https?://(?:localhost|127\.0\.0\.1):\d+[^\s\x1b]*', log)
                if match:
                    data['url'] = match.group()
                    data['show_tips'] = args.show_tips
                    data['panel_url'] = data['url'] if args.show_tips else launch_quiet_ui(data['url'], directory, proc.pid, data['pid_identity'])
                    open_panel(port, data['panel_url'])
                    write_json(directory / 'session.json', data)
                    emit({'status': 'ready', 'session_dir': str(directory), 'target': str(target), 'workspace': workspace, 'url': data['url']})
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Plannotator did not announce a URL within 45 seconds; inspect server.log.')
                time.sleep(.15)
            proc.wait()
        result = result_for(directory, data)
        emit(result)
        return 0 if result['status'] in ('completed', 'cancelled') else 1
    except KeyboardInterrupt:
        if proc and proc.poll() is None:
            cancel(directory, data)
            proc.wait(timeout=10)
        emit({'status': 'cancelled', 'session_dir': str(directory)})
        return 130
    except Exception as exc:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        write_json(directory / 'failure.json', {'error': str(exc)})
        emit({'status': 'failed', 'session_dir': str(directory), 'error': str(exc)})
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('doctor')
    for name in ('document', 'changes'):
        sub = subs.add_parser(name)
        sub.add_argument('target')
        sub.add_argument('--workspace')
        sub.add_argument('--owner')
        sub.add_argument('--show-tips', action='store_true', help='Show upstream first-use and feature introductions (normally skipped).')
        if name == 'changes':
            sub.add_argument('--base')
            sub.add_argument('--diff-type', choices=['since-base', 'local-vs-remote', 'uncommitted', 'staged', 'unstaged', 'last-commit', 'branch', 'merge-base', 'all'])
            sub.add_argument('--patch-file')
    for name in ('status', 'wait', 'ack', 'cancel', 'reopen'):
        sub = subs.add_parser(name)
        sub.add_argument('session_dir')
        if name == 'wait':
            sub.add_argument('--seconds', type=float, default=30)
        if name == 'reopen':
            sub.add_argument('--workspace')
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        code = code_cli()
        present = extension_present(code)
        emit({'binary': binary(), 'code_cli': code, 'extension_installed': present, 'registry': str(registry_path()), 'workspaces': registry(), 'ready': bool(binary() and present)})
        return 0 if binary() and present else 1
    if args.command in ('document', 'changes'):
        return start(args)
    directory, data = load_session(args.session_dir)
    if args.command == 'cancel':
        emit(cancel(directory, data))
    elif args.command == 'ack':
        result = result_for(directory, data)
        if result['status'] != 'completed':
            raise RuntimeError('Only a completed feedback result can be acknowledged.')
        if not (directory / 'handled.json').exists():
            write_json(directory / 'handled.json', {'at': now(), 'decision': result['result']['decision']})
        emit(result_for(directory, data))
    elif args.command == 'reopen':
        if not running(data) or not data.get('url'):
            raise RuntimeError('This service is no longer running; read its feedback before starting another round.')
        workspace, port = select_workspace(Path(data['target']), args.workspace or data['workspace'])
        if data.get('panel_url') and not data.get('show_tips', False):
            try:
                proxy = json.loads((directory / 'ui-proxy.json').read_text())
            except (OSError, ValueError):
                proxy = {}
            if not proxy.get('pid_identity') or process_identity(proxy.get('pid')) != proxy['pid_identity']:
                data['panel_url'] = launch_quiet_ui(data['url'], directory, data['pid'], data['pid_identity'])
        open_panel(port, data.get('panel_url', data['url']))
        data.update(workspace=workspace, ipc_port=port)
        write_json(directory / 'session.json', data)
        emit({'status': 'ready', 'session_dir': str(directory), 'workspace': workspace, 'url': data['url']})
    else:
        seconds = args.seconds if args.command == 'wait' else 0
        if not 0 <= seconds <= 60:
            raise RuntimeError('--seconds must be between 0 and 60; continue the same wait while user feedback is pending.')
        deadline = time.monotonic() + seconds
        while True:
            result = result_for(directory, data)
            if result['status'] != 'waiting' or time.monotonic() >= deadline:
                emit(result)
                break
            time.sleep(.2)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        emit({'status': 'failed', 'error': str(error)})
        sys.exit(1)

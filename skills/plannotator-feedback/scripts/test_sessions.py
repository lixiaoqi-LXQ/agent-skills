#!/usr/bin/env python3
"""Integration smoke test with the real CLI and a local VS Code IPC stand-in.

Does not open editor panels or external browsers. All fixtures are temporary.
"""
import http.server
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request

import review

SCRIPT = Path(__file__).with_name('review.py')


class Router(http.server.BaseHTTPRequestHandler):
    opened = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/open':
            self.opened.append(urllib.parse.parse_qs(parsed.query)['url'][0])
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'not found')


def request(base, path, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def main():
    if not review.binary():
        raise SystemExit('Install Plannotator before running this test.')
    router = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Router)
    thread = threading.Thread(target=router.serve_forever, daemon=True)
    thread.start()
    processes = []
    sessions = []
    try:
        with tempfile.TemporaryDirectory(prefix='plannotator-fixture-') as temp:
            root = Path(temp)
            (root / 'a.md').write_text('# Alpha\n\nAlpha sentence.\n')
            docs = root / 'docs'
            docs.mkdir()
            (docs / 'b.md').write_text('# Beta\n\nBeta sentence.\n')
            registry = root / 'registry.json'
            registry.write_text(json.dumps({str(root): router.server_port}))
            env = os.environ.copy()
            env['PLANNOTATOR_VSCODE_REGISTRY'] = str(registry)
            env['PLANNOTATOR_PORT'] = '19432'  # Must not leak into separate sessions.

            def start(mode, target, *options):
                p = subprocess.Popen([sys.executable, str(SCRIPT), mode, str(target), '--workspace', str(root), *options], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes.append(p)
                output = queue.Queue()

                def read():
                    for line in p.stdout:
                        output.put(json.loads(line))
                    output.put(None)

                threading.Thread(target=read, daemon=True).start()
                while True:
                    item = output.get(timeout=55)
                    if item is None:
                        raise AssertionError('Review exited before ready: ' + p.stderr.read())
                    if item['status'] == 'starting':
                        sessions.append(Path(item['session_dir']))
                    if item['status'] == 'failed':
                        raise AssertionError(item)
                    if item['status'] == 'ready':
                        return p, output, item

            def control(action, session, *extra):
                p = subprocess.run([sys.executable, str(SCRIPT), action, str(session), *extra], env=env, capture_output=True, text=True, timeout=10)
                assert p.returncode == 0, p.stdout + p.stderr
                return json.loads(p.stdout)

            a, aq, ar = start('document', root / 'a.md', '--owner', 'agent-a')
            b, bq, br = start('document', docs, '--owner', 'agent-b')
            assert ar['session_dir'] != br['session_dir'] and ar['url'] != br['url']
            assert ':19432' not in ar['url'] and ':19432' not in br['url']
            for result, owner in [(ar, 'agent-a'), (br, 'agent-b')]:
                s = Path(result['session_dir'])
                meta = json.loads((s / 'session.json').read_text())
                assert meta['owner'] == owner and (s / 'data').is_dir()
                assert s.stat().st_mode & 0o077 == 0
            request(ar['url'], '/api/external-annotations', {'source': 'selftest', 'type': 'COMMENT', 'originalText': 'Alpha sentence.', 'text': 'Only agent A receives this.'})
            assert len(request(ar['url'], '/api/external-annotations')['annotations']) == 1
            assert request(br['url'], '/api/external-annotations')['annotations'] == []
            assert control('wait', ar['session_dir'], '--seconds', '0')['status'] == 'waiting'
            request(br['url'], '/api/feedback', {'feedback': 'Only agent B feedback.', 'annotations': []})
            bresult = bq.get(timeout=15)
            assert bresult['status'] == 'completed' and 'Only agent B' in bresult['result']['feedback']
            assert control('status', ar['session_dir'])['status'] == 'waiting'
            request(ar['url'], '/api/feedback', {'feedback': 'Only agent A feedback.', 'annotations': []})
            aresult = aq.get(timeout=15)
            assert aresult['status'] == 'completed' and 'Only agent A' in aresult['result']['feedback']
            assert 'Only agent B' not in aresult['result']['feedback']
            assert control('ack', ar['session_dir'])['handled']
            assert control('ack', ar['session_dir'])['handled']
            print('PASS: file/folder sessions, separate ports/data/feedback, waiting and idempotent ack', flush=True)

            c, cq, cr = start('document', root / 'a.md')
            peer, peerq, peerr = start('document', docs)
            assert control('reopen', cr['session_dir'])['url'] == cr['url']
            assert control('cancel', cr['session_dir'])['status'] == 'cancelled'
            c.wait(timeout=10)
            assert control('status', cr['session_dir'])['status'] == 'cancelled'
            assert control('status', peerr['session_dir'])['status'] == 'waiting'
            request(peerr['url'], '/api/feedback', {'feedback': 'Looks good', 'annotations': []})
            assert peerq.get(timeout=15)['status'] == 'completed'
            print('PASS: reopen existing service and cancel while another session remains usable', flush=True)

            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
            git('init')
            git('config', 'user.name', 'Review Test')
            git('config', 'user.email', 'test@example.invalid')
            (repo / 'readme.md').write_text('before\n')
            git('add', 'readme.md')
            git('commit', '-m', 'fixture')
            (repo / 'readme.md').write_text('after\n')
            d, dq, dr = start('changes', repo)
            # Code review adds an approved flag and returns message, not feedback.
            request(dr['url'], '/api/feedback', {'approved': False, 'feedback': 'Review mode feedback.', 'annotations': []})
            dresult = dq.get(timeout=15)
            assert dresult['status'] == 'completed' and 'message' in dresult['result'], dresult
            print('PASS: real Git changes review returns decision/message JSON', flush=True)
            e, eq, er = start('changes', repo)
            request(er['url'], '/api/feedback', {'approved': True, 'feedback': 'Ready', 'annotations': []})
            eresult = eq.get(timeout=15)
            assert eresult['status'] == 'completed' and eresult['result']['decision'] == 'approved', eresult
            print('PASS: approved changes review is preserved', flush=True)
            assert len(Router.opened) == 7  # Six services and one reopen.
            print('All integration checks passed. No external browser was opened.', flush=True)
    finally:
        for session in sessions:
            try:
                directory, meta = review.load_session(session)
                if review.running(meta):
                    review.cancel(directory, meta)
            except Exception:
                pass
        for p in processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.terminate()
                p.wait(timeout=5)
        for session in sessions:
            directory, meta = review.load_session(session)
            if not review.running(meta):
                shutil.rmtree(directory)
        router.shutdown()
        router.server_close()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Exercise notice initialization, binary/JSON forwarding and streaming."""
import http.client
import http.server
import json
import shutil
import subprocess
import threading
import time
import unittest
import urllib.request

from quiet_ui import NOTICE_FLAGS, inject_notices, make_handler


class Upstream(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            self.wfile.write(b'data: ready\n\n')
            self.wfile.flush()
            time.sleep(1.5)
            return
        body = b'\x89PNG\r\n\x1a\n\x00\xff' if self.path == '/image' else b'<html><head><script type="module">app()</script></head><body>Review</body></html>'
        self.send_response(200)
        self.send_header('Content-Type', 'image/png' if self.path == '/image' else 'text/html')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.headers.get('Transfer-Encoding') == 'chunked':
            chunks = []
            while True:
                size = int(self.rfile.readline().strip(), 16)
                if not size:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.read(2)
            body = b''.join(chunks)
        else:
            body = self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)


class QuietUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        cls.gateway = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(f'http://127.0.0.1:{cls.upstream.server_port}'))
        cls.gateway.daemon_threads = True
        for server in (cls.upstream, cls.gateway):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.gateway.server_port}'

    @classmethod
    def tearDownClass(cls):
        for server in (cls.gateway, cls.upstream):
            server.shutdown()
            server.server_close()

    def test_injected_shell_and_original_binary(self):
        html = urllib.request.urlopen(self.base).read().decode()
        self.assertIn('data-plannotator-feedback-quiet-tips', html)
        self.assertLess(html.index('data-plannotator-feedback-quiet-tips'), html.index('</head>'))
        self.assertEqual(urllib.request.urlopen(self.base + '/image').read(), b'\x89PNG\r\n\x1a\n\x00\xff')

    def test_feedback_body_is_unchanged(self):
        body = json.dumps({'feedback': '用户意见', 'approved': False}).encode()
        response = urllib.request.urlopen(urllib.request.Request(self.base + '/api/feedback', data=body, headers={'Content-Type': 'application/json'}))
        self.assertEqual(response.read(), body)

    def test_chunked_feedback_body_is_unchanged(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.gateway.server_port, timeout=5)
        chunks = [b'{"feedback":"', '批注'.encode(), b'","approved":false}']
        try:
            connection.request('POST', '/api/feedback', body=iter(chunks), encode_chunked=True)
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b''.join(chunks))
        finally:
            connection.close()

    def test_stream_arrives_before_response_ends(self):
        start = time.monotonic()
        with urllib.request.urlopen(self.base + '/stream') as response:
            self.assertEqual(response.readline(), b'data: ready\n')
            self.assertLess(time.monotonic() - start, 1.2)

    @unittest.skipUnless(shutil.which('node'), 'Node is only needed to validate the browser prelude')
    def test_stale_cookie_snapshot_does_not_reenable_tours(self):
        html = inject_notices('<html><head></head><body></body></html>')
        script = html.split('<script data-plannotator-feedback-quiet-tips>', 1)[1].split('</script>', 1)[0]
        harness = '''const vm = require('node:vm');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const outcomes=[];
for(let round=0;round<2;round++){
  const cookies={'plannotator-identity':'same-user','plannotator-guide-intro-seen':'old','plannotator-auto-update-notice-seen':'unchanged'};
  const document={};
  Object.defineProperty(document,'cookie',{get:()=>Object.entries(cookies).map(([k,v])=>k+'='+v).join('; '),set:s=>{const pair=s.split(';')[0];const i=pair.indexOf('=');cookies[pair.slice(0,i)]=decodeURIComponent(pair.slice(i+1));}});
  vm.runInNewContext(input.script,{document});outcomes.push(cookies);
}
process.stdout.write(JSON.stringify(outcomes));'''
        process = subprocess.run(['node', '-e', harness], input=json.dumps({'script': script}), capture_output=True, text=True, check=True)
        for cookies in json.loads(process.stdout):
            for key, value in NOTICE_FLAGS.items():
                self.assertEqual(cookies[key], value)
            self.assertEqual(cookies['plannotator-identity'], 'same-user')
            self.assertEqual(cookies['plannotator-auto-update-notice-seen'], 'unchanged')
            self.assertFalse(any('permission' in k or 'approve' in k for k in NOTICE_FLAGS))


if __name__ == '__main__':
    unittest.main()

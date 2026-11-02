#!/usr/bin/env python3
"""Session-local UI gateway: skip known instructional notices, preserve review APIs.

Flags are from Plannotator 0.28.44. This does not hide dialogs or acknowledge
approval, permission, conflict, failure, or update-error prompts.
"""
import argparse
import http.client
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.parse

NOTICE_FLAGS = {
    'plannotator-plan-look-v2': 'resolved',
    'plannotator-plan-look-choice-resolved': 'true',
    'plannotator-look-feel-announcement-seen': '2',
    'plannotator-guide-intro-seen': '2',
    'plannotator-guide-hint-acked': 'true',
    'plannotator-edit-mode-announcement-seen': '3',
    'plannotator-token-hover-announcement-seen': '1',
    'plannotator-review-dest-spotlight-seen': '1',
    'plannotator-auto-viewed-notice-seen': '1',
    'plannotator-announce-tui-herdr-seen': '1',
    'plannotator-announce-inbox-seen': '1',
    'plannotator-announce-ask-session-seen': '1',
    'plannotator-announce-agent-tool-seen': '1',
}
HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade', 'content-length'}


def inject_notices(html):
    script = '<script data-plannotator-feedback-quiet-tips>(function(){const flags=' + json.dumps(NOTICE_FLAGS) + ';for(const [key,value] of Object.entries(flags)){document.cookie=key+"="+encodeURIComponent(value)+"; path=/; max-age=31536000; SameSite=Lax";}})();</script>'
    # The official extension prepends its cookie shim immediately after <head>.
    # Our later prelude therefore writes through that shim before React mounts.
    if '</head>' not in html:
        raise ValueError('Plannotator HTML has no head; cannot initialize notice flags.')
    return html.replace('</head>', script + '</head>', 1)


def make_handler(upstream):
    parsed = urllib.parse.urlsplit(upstream)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1'):
        raise ValueError('Expected a loopback HTTP upstream.')

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def forward(self):
            connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=90)
            sent = False
            try:
                transfer = self.headers.get('Transfer-Encoding', '').lower()
                if transfer and transfer != 'chunked':
                    self.send_error(501, 'Unsupported transfer encoding')
                    return
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0 or (transfer and self.headers.get('Content-Length')):
                    self.send_error(400, 'Invalid request framing')
                    return

                def request_body():
                    remaining = length
                    while remaining or transfer:
                        if transfer:
                            line = self.rfile.readline(65537)
                            if len(line) > 65536 or not line.endswith(b'\r\n'):
                                raise ValueError('Invalid chunk header')
                            remaining = int(line.split(b';', 1)[0].strip(), 16)
                            if remaining < 0:
                                raise ValueError('Invalid chunk size')
                            if remaining == 0:
                                while True:
                                    trailer = self.rfile.readline(65537)
                                    if trailer == b'\r\n':
                                        return
                                    if not trailer or len(trailer) > 65536:
                                        raise ValueError('Invalid chunk trailer')
                        while remaining:
                            block = self.rfile.read(min(remaining, 65536))
                            if not block:
                                raise ValueError('Incomplete request body')
                            remaining -= len(block)
                            yield block
                        if transfer and self.rfile.read(2) != b'\r\n':
                            raise ValueError('Invalid chunk terminator')

                body = request_body() if length or transfer else None
                headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_HEADERS}
                headers.update({'Host': parsed.netloc, 'Accept-Encoding': 'identity'})
                if not transfer and self.headers.get('Content-Length') is not None:
                    headers['Content-Length'] = str(length)
                connection.request(self.command, self.path, body=body, headers=headers, encode_chunked=bool(transfer))
                response = connection.getresponse()
                is_shell = (self.command == 'GET' and urllib.parse.urlsplit(self.path).path in ('/', '/index.html')
                            and 'text/html' in response.getheader('Content-Type', ''))
                rewritten = inject_notices(response.read().decode('utf-8')).encode('utf-8') if is_shell else None
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in HOP_HEADERS and (not is_shell or name.lower() not in {'content-encoding', 'etag'}):
                        self.send_header(name, value)
                self.send_header('Connection', 'close')
                if rewritten is not None:
                    self.send_header('Content-Length', str(len(rewritten)))
                self.end_headers()
                sent = True
                if rewritten is not None:
                    self.wfile.write(rewritten)
                elif self.command != 'HEAD':
                    while True:
                        chunk = response.read1(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
            except (OSError, ValueError, http.client.HTTPException) as exc:
                if not sent:
                    self.send_error(502, 'Plannotator UI gateway unavailable')
                print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr, flush=True)
            finally:
                self.close_connection = True
                connection.close()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = forward

    return Handler


def launch(upstream, directory, pid, identity):
    output = directory / 'ui-proxy.json'
    output.unlink(missing_ok=True)
    with (directory / 'ui-proxy.log').open('a') as log:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--upstream', upstream,
                                 '--state-file', str(output), '--pid', str(pid), '--identity', identity],
                                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if output.exists():
            return json.loads(output.read_text())['url']
        if proc.poll() is not None:
            break
        time.sleep(.05)
    proc.terminate()
    proc.wait(timeout=5)
    raise RuntimeError('Quiet UI gateway failed; inspect ui-proxy.log.')


def main():
    from review import process_identity, write_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--state-file', type=Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--identity', required=True)
    args = parser.parse_args()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), make_handler(args.upstream))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    parsed = urllib.parse.urlsplit(args.upstream)
    url = urllib.parse.urlunsplit(('http', f'127.0.0.1:{server.server_port}', parsed.path, parsed.query, parsed.fragment))
    write_json(args.state_file, {'url': url, 'pid': os.getpid(), 'pid_identity': process_identity(os.getpid())})
    try:
        while process_identity(args.pid) == args.identity:
            time.sleep(.5)
        # Let an in-flight Send Feedback response drain after its upstream exits.
        time.sleep(2)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()

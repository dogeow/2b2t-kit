"""Loopback-only Chinese UI for Harness² snapshot diagnostics."""
from __future__ import annotations

import argparse
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from minecraft_harness import ADOPTED, DEFAULT_TASK, KIT, RULES, editor_prompt, write

HERE = Path(__file__).resolve().parent
RUNS = KIT / 'work/harness2-ui'
PREVIOUS = KIT / 'work/harness2-iron-farm-20261019/iteration-2'
SAVED = KIT / 'work/harness2-iron-farm-20261019/snapshot.json'
PYTHON = KIT.parent / 'harness2/.venv/bin/python'
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
ACTIVE = None


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def view_run(root):
    validation = read_json(root / 'integration-validation.json')
    handoff = read_json(root / 'adopted-handoff.json') or read_json(root / 'local-handoff.json')
    audit = root / 'codex-audit'
    stages = []
    for stage in ('inv1.a1', 'dom1.a1', 'c1.a1', 'experience.seq1'):
        directory = audit / stage
        if directory.exists():
            answer = read_json(directory / 'answer.json')
            stages.append({'id': stage, 'done': bool(answer), 'text': answer.get('text', '') if answer else ''})
    reflection = read_json(audit / 'experience.seq1/answer.json', {})
    inputs = read_json(audit / 'c1.a1/input.json') or read_json(audit / 'inv1.a1/input.json')
    prompt = editor_prompt(inputs['mission'], inputs['context']) if inputs else ''
    return {'validation': validation, 'handoff': handoff, 'stages': stages,
            'reflection': reflection.get('text', ''), 'actual_prompt': prompt,
            'path': str(root)}


def run_job(root, mode, source):
    global ACTIVE
    job = read_json(root / 'job.json')
    try:
        script = str(HERE / 'minecraft_harness.py')
        snapshot = root / 'snapshot.json'
        with (root / 'run.log').open('w') as output:
            if source == 'live':
                subprocess.run([str(PYTHON), script, 'capture', '--output', str(snapshot)],
                               cwd=KIT, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=30)
            else:
                shutil.copyfile(SAVED, snapshot)
            job.update(state='running', detail='正在本地检查' if mode == 'local' else '正在进行 Codex 策略修改、比较与反思')
            write(root / 'job.json', job)
            if mode == 'local':
                argv = [str(PYTHON), script, 'probe', '--snapshot', str(snapshot), '--output', str(root / 'local-handoff.json')]
            else:
                argv = [str(PYTHON), script, 'run', '--snapshot', str(snapshot), '--output', str(root),
                        '--prompt-file', str(root / 'task.txt'), '--allow-snapshot-upload']
            subprocess.run(argv, cwd=KIT, stdout=output, stderr=subprocess.STDOUT, check=True, timeout=1200)
        job.update(state='complete', detail='本地检查完成' if mode == 'local' else 'Codex 改进与验收完成')
    except Exception as exc:
        # Keep the last known result separate from failures. Never imply an old run succeeded now.
        job.update(state='failed', detail='本次未完成，请查看运行记录。游戏未接管。', error=str(exc))
    finally:
        job['finished_at'] = int(time.time() * 1000)
        write(root / 'job.json', job)
        with LOCK:
            ACTIVE = None


def start_job(body):
    global ACTIVE
    mode, source, prompt = body.get('mode'), body.get('source'), body.get('prompt')
    if mode not in ('local', 'model') or source not in ('live', 'saved'):
        raise ValueError('请选择运行方式和快照来源')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 6000:
        raise ValueError('任务描述需为 1–6000 个字符')
    if mode == 'model' and body.get('allow_upload') is not True:
        raise ValueError('请明确允许将本次快照发送至 Codex/ChatGPT')
    with LOCK:
        if ACTIVE is not None:
            raise ValueError('已有任务正在运行，请等待完成')
        identity = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
        root = RUNS / identity
        root.mkdir(parents=True)
        (root / 'task.txt').write_text(prompt.strip())
        job = {'id': identity, 'mode': mode, 'source': source, 'state': 'starting',
               'prompt': prompt.strip(), 'started_at': int(time.time() * 1000),
               'detail': '正在读取游戏快照' if source == 'live' else '正在读取已保存快照',
               'allow_upload': body.get('allow_upload') is True}
        write(root / 'job.json', job)
        ACTIVE = identity
        threading.Thread(target=run_job, args=(root, mode, source), daemon=True).start()
        return job


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, value, content_type='application/json; charset=utf-8'):
        data = value.encode() if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def host_ok(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {'error': '仅允许本机访问'})
        if self.path == '/':
            return self.send(200, (HERE / 'ui.html').read_text().replace('__TOKEN__', TOKEN), 'text/html; charset=utf-8')
        if self.path == '/api/state':
            from live_view import state as live_state
            jobs = sorted(RUNS.glob('*/job.json'), reverse=True)[:12]
            latest = jobs[0].parent if jobs else None
            saved = read_json(SAVED, {})
            return self.send(200, {'live_strategy': live_state(KIT / 'work/harness2-live'),
                                   'active': ACTIVE, 'default_prompt': DEFAULT_TASK, 'rules': RULES,
                                   'saved_at': saved.get('captured_at_ms'),
                                   'jobs': [read_json(p) for p in jobs],
                                   'current': view_run(latest) if latest else None,
                                   'verified_example': view_run(PREVIOUS),
                                   'adopted': read_json(ADOPTED)})
        if self.path == '/api/log':
            jobs = sorted(RUNS.glob('*/job.json'), reverse=True)
            path = jobs[0].parent / 'run.log' if jobs else None
            return self.send(200, {'text': path.read_text()[-16000:] if path and path.exists() else '暂无运行记录'})
        return self.send(404, {'error': '未找到页面'})

    def do_POST(self):
        origin = self.headers.get('Origin')
        allowed = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
        if not self.host_ok() or (origin is not None and origin not in allowed) or self.headers.get('X-Harness-Token') != TOKEN:
            return self.send(403, {'error': '请求来源验证失败'})
        if self.path != '/api/jobs':
            return self.send(404, {'error': '未找到操作'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32000:
                raise ValueError('请求过大或为空')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('请求格式错误')
            return self.send(202, start_job(body))
        except (ValueError, TypeError) as exc:
            return self.send(400, {'error': str(exc)})


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--port', type=int, default=18768)
    parser.add_argument('--open', action='store_true', help='Open the local UI in the default browser')
    args = parser.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    lock = (RUNS / 'ui.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if args.open:
            webbrowser.open(f'http://127.0.0.1:{args.port}')
            return
        raise
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Harness² 界面：http://127.0.0.1:{args.port}', flush=True)
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    server.serve_forever()


if __name__ == '__main__':
    main()

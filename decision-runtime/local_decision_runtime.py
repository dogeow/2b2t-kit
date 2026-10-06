"""Kit-managed persistent local decision service; never controls the player."""
import argparse
import fcntl
import json
import os
import signal
import subprocess
import time
from pathlib import Path
import httpx
from decisions import validated_answer
from ollama_decision import BASE, MODELS, checked_image
from decision_prompt import questions

STOP = False


def atomic(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def valid_config(config):
    if (config.get('provider') != 'ollama' or config.get('local_model') not in MODELS
            or type(config.get('enabled')) is not bool or type(config.get('keep_loaded')) is not bool
            or type(config.get('context_length')) is not int or config['context_length'] not in (2048, 4096, 8192)):
        raise ValueError('Invalid local decision settings')
    return config


def prepare(client, config):
    name = config['local_model']
    alias = MODELS[name]
    tags = client.get('/api/tags').json().get('models', [])
    if not any(m['name'] in (name, name + ':latest') for m in tags):
        raise RuntimeError('Selected model is not installed; no automatic download')
    existing = client.get('/api/ps').json().get('models', [])
    if any(m['name'].split(':')[0] not in MODELS.values() for m in existing):
        raise RuntimeError('Another user model is resident; it was not evicted')
    for item in existing:
        if item['name'].split(':')[0] != alias:
            client.post('/api/generate', json={'model': item['name'], 'keep_alive': 0}).raise_for_status()
    response = client.post('/api/create', json={'model': alias, 'from': name,
                          'parameters': {'num_ctx': config['context_length']}, 'stream': False})
    response.raise_for_status()
    warm = {'model': alias, 'state': {'purpose': 'Preload Kit decision runtime. No game action.'},
            'questions': {'ready': {'type': 'noul', 'instructions': 'Is this a runtime preloading request?'}},
            'keep_alive': -1 if config['keep_loaded'] else 0}
    try:
        client.post('/v1/systemone', json=warm).raise_for_status()
        loaded = client.get('/api/ps').json().get('models', [])
        matching = [m for m in loaded if m['name'].split(':')[0] == alias]
        if config['keep_loaded'] and (len(matching) != 1 or not config['context_length'] <= matching[0].get('context_length',0) <= config['context_length']+32):
            raise RuntimeError('Configured model context was not applied')
    except Exception:
        try:
            client.post('/api/generate', json={'model': alias, 'keep_alive': 0}, timeout=8).raise_for_status()
        except httpx.HTTPError:
            pass
        raise
    return alias, matching[0].get('size_vram', 0) if matching else 0


def probe(client, automation, config, request):
    state = json.loads((automation / 'status.json').read_text())
    image = checked_image(request['image'], automation, state)
    options = {'world': 'A Minecraft world scene with terrain or sky is visible.',
               'menu': 'A menu, settings screen, or disconnect dialog is visible.',
               'unclear': 'The screenshot does not support either classification.'}
    start = time.perf_counter()
    payload = {'model': MODELS[config['local_model']],
               'state': {'goal': 'Classify this native game frame. Do not execute any action.'},
               'images': [image], 'questions': questions(options), 'keep_alive': -1 if config['keep_loaded'] else 0}
    response = client.post('/v1/systemone', json=payload)
    response.raise_for_status()
    answer = validated_answer(response.json(), options)
    return {'choice': answer['choice'], 'confidence': answer['confidence'],
            'elapsed_ms': round((time.perf_counter() - start) * 1000), 'game_actions_dispatched': False}


def serve(game, parent_pid):
    global STOP
    folder = game / 'config/twob2tkit/decision-advisor'
    folder.mkdir(parents=True, exist_ok=True)
    lock = (folder / 'service.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    server = None
    loaded_alias = None
    applied = None
    try:last_control=json.loads((folder/'control.json').read_text()).get('id')
    except (OSError,ValueError):last_control=None
    next_retry = 0
    next_residency_check = 0
    latest_test = None
    client = httpx.Client(base_url=BASE, trust_env=False, follow_redirects=False,
                         timeout=httpx.Timeout(120, connect=2))
    try:
        while not STOP:
            if parent_pid:
                try:
                    os.kill(parent_pid, 0)
                except ProcessLookupError:
                    break
            try:
                config = json.loads((folder / 'settings.json').read_text())
                if config.get('provider')!='ollama' or not config.get('enabled'):
                    break
                config=valid_config(config)
                if not config['enabled']:
                    break
                control = folder / 'control.json'
                request = json.loads(control.read_text()) if control.exists() else {}
                if request.get('id') != last_control and request.get('kind') == 'stop':
                    break
                signature = (config['local_model'], config['context_length'], config['keep_loaded'])
                if signature != applied and time.monotonic() >= next_retry:
                    atomic(folder / 'runtime.json', {'phase': 'warming', 'time': time.time(), 'pid': os.getpid(),
                                                    'model': MODELS[config['local_model']]})
                    try:
                        client.get('/api/version').raise_for_status()
                    except httpx.HTTPError:
                        binary = Path('/opt/homebrew/bin/ollama')
                        if not binary.is_file():
                            raise RuntimeError('Ollama executable is unavailable')
                        log_path = folder / 'ollama-service.log'
                        log = log_path.open('ab')
                        os.chmod(log_path, 0o600)
                        env = {**os.environ, 'OLLAMA_HOST': '127.0.0.1:11434',
                               'OLLAMA_MAX_LOADED_MODELS': '1', 'OLLAMA_NUM_PARALLEL': '1'}
                        server = subprocess.Popen([str(binary), 'serve'], env=env, stdout=log, stderr=log,
                                                  start_new_session=True)
                        log.close()
                        for _ in range(40):
                            try:
                                client.get('/api/version').raise_for_status()
                                break
                            except httpx.HTTPError:
                                time.sleep(.25)
                        else:
                            raise RuntimeError('Ollama did not become available')
                    with (folder / 'inference.lock').open('a') as inference:
                        fcntl.flock(inference, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        loaded_alias, size = prepare(client, config)
                    applied = signature
                if applied == signature:
                    if (request.get('kind') == 'probe_image' and request.get('id') != last_control
                            and config['local_model'] == 'clef-flash'):
                        last_control = request['id']
                        with (folder / 'inference.lock').open('a') as inference:
                            try:
                                fcntl.flock(inference, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                latest_test = probe(client, game / 'config/twob2tkit/automation', config, request)
                            except Exception as exc:
                                latest_test = {'error_type': type(exc).__name__, 'game_actions_dispatched': False}
                    if time.monotonic() >= next_residency_check:
                        residents = client.get('/api/ps').json().get('models', [])
                        own = [m for m in residents if m['name'].split(':')[0] == loaded_alias]
                        if config['keep_loaded'] and len(own) != 1:
                            raise RuntimeError('Configured resident model is unavailable')
                        size = own[0].get('size_vram', 0) if own else 0
                        next_residency_check = time.monotonic() + 5
                    atomic(folder / 'runtime.json', {'phase': 'ready', 'time': time.time(), 'pid': os.getpid(),
                          'model': loaded_alias, 'context_length': config['context_length'],
                          'resident_bytes': size, 'keep_loaded': config['keep_loaded'], 'last_test': latest_test})
            except Exception as exc:
                atomic(folder / 'runtime.json', {'phase': 'error', 'time': time.time(), 'pid': os.getpid(),
                                                'error_type': type(exc).__name__, 'detail': str(exc).split('https://')[0][:180]})
                applied = None
                next_retry = time.monotonic() + 30
            time.sleep(1)
    finally:
        if loaded_alias:
            try:
                client.post('/api/generate', json={'model': loaded_alias, 'keep_alive': 0}, timeout=8).raise_for_status()
            except httpx.HTTPError:
                pass
        client.close()
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
        atomic(folder / 'runtime.json', {'phase': 'stopped', 'time': time.time(), 'resident_bytes': 0})
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--parent-pid', type=int)
    args = parser.parse_args()
    def stop(*_):
        global STOP
        STOP = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    serve(args.game, args.parent_pid)

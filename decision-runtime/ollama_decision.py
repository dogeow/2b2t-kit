"""Loopback-only System One adapter. No gameplay or service startup in inference."""
import base64
import fcntl
import hashlib
import json
import struct
import time
from pathlib import Path
import httpx
from decisions import DecisionError

BASE = 'http://127.0.0.1:11434'
MODELS = {'nimble': 'kit-nimble', 'clef-flash': 'kit-clef-flash'}


def checked_image(proof, automation, state, max_age=15):
    """Accept only a fresh, scoped PNG emitted by Kit's framebuffer capture."""
    if not isinstance(proof, dict) or proof.get('source') != 'kit_framebuffer':
        raise DecisionError('Missing native image provenance')
    if (proof.get('world_session') != state.get('world_session')
            or proof.get('control_revision') != state.get('control_revision')
            or proof.get('screen') != ''
            or type(proof.get('captured_at')) is not int
            or not 0 <= time.time() - proof['captured_at'] / 1000 <= max_age):
        raise DecisionError('Game image is stale or belongs to another controller')
    path = Path(proof.get('path', ''))
    folder = Path(automation).resolve() / 'decision-images'
    if (path.is_symlink() or path.suffix != '.png' or path.resolve().parent != folder
            or not path.is_file() or not 64 <= path.stat().st_size <= 1_048_576):
        raise DecisionError('Game image must be a bounded native PNG')
    raw = path.read_bytes()
    if raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
        raise DecisionError('Invalid native PNG')
    width, height = struct.unpack('>II', raw[16:24])
    if (not 1 <= width <= 640 or not 1 <= height <= 360
            or [width, height] != [proof.get('width'), proof.get('height')]
            or hashlib.sha256(raw).hexdigest() != proof.get('sha256')):
        raise DecisionError('Game image dimensions or checksum differ')
    return base64.b64encode(raw).decode('ascii')


class OllamaDecision:
    def __init__(self, settings_dir, config, image=None, client=None):
        self.settings_dir = Path(settings_dir)
        self.config = config
        base_model = config.get('local_model', 'clef-flash')
        if base_model not in MODELS:
            raise DecisionError('Unsupported Kit local decision model')
        self.model = MODELS[base_model]
        self.image = image
        if image and base_model != 'clef-flash':
            raise DecisionError('Selected model does not support images')
        self.client = client or httpx.Client(base_url=BASE, trust_env=False, follow_redirects=False,
                                            timeout=httpx.Timeout(config['timeout_seconds'], connect=2))

    def predict(self, state, questions):
        runtime = self.settings_dir / 'runtime.json'
        try:
            ready = json.loads(runtime.read_text())
        except (OSError, ValueError):
            raise DecisionError('Kit local decision service is not ready') from None
        if (ready.get('phase') != 'ready' or ready.get('model') != self.model
                or ready.get('context_length') != self.config['context_length']
                or time.time() - ready.get('time', 0) > 20):
            raise DecisionError('Kit local decision service is warming or changed')
        payload = {'model': self.model, 'state': state, 'questions': questions,
                   'keep_alive': -1 if self.config['keep_loaded'] else 0}
        # A byte bound is deliberately conservative. Never silently crop facts.
        text = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf8')
        limit = self.config['context_length'] - (1792 if self.image else 256)
        if len(text) > limit:
            raise DecisionError('Local decision context exceeds the explicit budget')
        if self.image:
            payload['images'] = [self.image]
        lock = (self.settings_dir / 'inference.lock').open('a')
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DecisionError('Another Kit decision is still in flight') from None
            try:
                response = self.client.post('/v1/systemone', json=payload)
            except httpx.HTTPError:
                raise DecisionError('Local decision request failed') from None
            if response.status_code != 200 or len(response.content) > 1_000_000:
                raise DecisionError('Local decision response is unavailable or too large')
            result = response.json()
            if result.get('model') != self.model:
                raise DecisionError('Local decision returned another model')
            return result
        finally:
            lock.close()

    def close(self):
        # Resident-model lifetime is managed by the Kit service, not a stage.
        self.client.close()

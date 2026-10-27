"""Harness² experiments over immutable Kit evidence; never a second game controller."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

KIT = Path(__file__).resolve().parents[2]
UPSTREAM = KIT.parent / 'harness2'
ADOPTED = KIT / 'work/harness2-adopted/iron-farm.json'
sys.path.insert(0, str(KIT / 'decision-runtime'))
from harness2.core import tree
from harness2.core.proposer import Proposer, ProposerError, Reply
from harness2.core.schedule import run_domain
from harness2.core.spec import BenchPrompts, BenchSpec, ChannelSpec
from harness2.substrate.codex import CodexSubstrate

ALLOWED = frozenset({'AGENTS.md', 'scripts/policy.py'})
CHECKS = frozenset({'live_state', 'villagers', 'hostile', 'water', 'production', 'unknown_actions'})
RULES = '''Use only supplied Minecraft evidence. Historical construction records are not a live survey.
Never control Minecraft, change game files, restart, reconnect, read credentials, use Notion,
spawn agents, or replay unknown actions. Keep the existing Kit sole action controller.
Only produce an evidence-based handoff. A running farm requires real golems and new iron
in its collection chest. Existing inventory iron does not establish farm production.
'''
DEFAULT_TASK = '根据现场快照检查当前刷铁机还缺哪些条件，列出可验证的下一步。保留已锁定交易的村民，区分历史记录与当前证据；本轮只诊断，不操作游戏。'


def editor_prompt(mission, documents):
    prompt = RULES + '\nYou are the Harness2 editor. All context is supplied below; do not use tools.\n'
    prompt += 'Return JSON text and files. For editing return both approved files in files; retain immutable rules verbatim. '
    prompt += 'scripts/policy.py must contain exactly CHECKS = [literal string names]. Only change the checks list to select useful checks: ' + ', '.join(sorted(CHECKS)) + '. '
    prompt += 'For selection/experience return no files and follow the requested choice/XML format in text. '
    return prompt + 'Evidence-supported lessons remain in this project run library only.\n' + mission + '\n' + json.dumps(documents)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def validate_policy(files):
    if set(files) != ALLOWED or RULES not in files['AGENTS.md']:
        raise ValueError('Keep the two approved files and immutable execution boundaries')
    node = ast.parse(files['scripts/policy.py'])
    if len(node.body) != 1 or not isinstance(node.body[0], ast.Assign) or len(node.body[0].targets) != 1 or not isinstance(node.body[0].targets[0], ast.Name) or node.body[0].targets[0].id != 'CHECKS':
        raise ValueError('Only a literal CHECKS assignment is allowed; no executable code')
    policy = {'checks': ast.literal_eval(node.body[0].value)}
    if set(policy) != {'checks'} or not isinstance(policy['checks'], list):
        raise ValueError('Policy must contain only a checks list')
    if any(c not in CHECKS for c in policy['checks']) or len(set(policy['checks'])) != len(policy['checks']):
        raise ValueError('Unknown or duplicate check; executable model scripts are not accepted')
    return policy


def assess(evidence, checks):
    """Conservative deterministic probes; unknowns are never converted into success."""
    farm = evidence['recorded_project']['iron_farm']
    state = evidence['live_state']
    findings = []
    for check in checks:
        if check == 'live_state':
            findings.append({'check': check, 'status': 'requires_new_live_survey',
                             'detail': 'This immutable snapshot cannot authorize future game input.',
                             'captured_world': state.get('world_session'),
                             'captured_health': state.get('health')})
        elif check == 'villagers':
            findings.append({'check': check, 'status': 'not_live_verified',
                             'recorded_imported': farm.get('dedicated_villagers_imported'),
                             'required': farm.get('dedicated_villagers_required'),
                             'next': 'Survey housing and preserve locked traders before moving dedicated candidates.'})
        elif check == 'hostile':
            findings.append({'check': check, 'status': 'not_live_verified',
                             'recorded_captured': farm.get('hostile_captured'),
                             'next': 'Verify sealed sun-protected chamber, then capture a persistent hostile safely.'})
        elif check == 'water':
            findings.append({'check': check, 'status': 'recorded_blocked',
                             'recorded_release_completed': farm.get('water_release_completed'),
                             'next': 'Do not restart or replace the deferred host patch; survey dry work that can proceed.'})
        elif check == 'production':
            findings.append({'check': check, 'status': 'unproven',
                             'recorded_production_credit': farm.get('production_credit'),
                             'next': 'Observe spawned golems and collection-chest iron increase with before/after evidence.'})
        elif check == 'unknown_actions':
            findings.append({'check': check, 'status': 'retain_without_replay',
                             'markers': evidence['unresolved_actions']})
    return {'mode': 'snapshot_probe_only', 'farm_operational_verified': False,
            'live_actions_executed': 0, 'findings': findings,
            'snapshot_sha256': evidence['snapshot_sha256']}


def capture(root, project, destination):
    from live_snapshot import read_fresh
    state = read_fresh(root)
    if not state.get('connected') or state.get('manual_movement') or state.get('screen') or state.get('health', 0) < 19:
        raise RuntimeError('Capture requires a connected, healthy, idle game with no open interface')
    data = json.loads(project.read_text())
    names = ['unresolved-boat-placement.json', 'unresolved-link-step-placement.json', 'retained-printer-outcome.json']
    unresolved = {}
    for name in names:
        path = project.parent / name
        if path.exists():
            value = json.loads(path.read_text())
            unresolved[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                'outcome_unresolved': value.get('outcome_unresolved'), 'pending': value.get('pending')}
    result = {'captured_at_ms': int(time.time() * 1000),
              'live_state': {k: state.get(k) for k in ['time', 'world_session', 'connected', 'health', 'pos', 'kit_version',
                                                      'runtime_version', 'loaded_villagers', 'supervision_lease']},
              'recorded_project': {'iron_farm': data['iron_farm'],
                                   'workstation_installation_gate': data['workstation_installation_gate']},
              'unresolved_actions': unresolved,
              'provenance': {'project_path': str(project.resolve()),
                             'project_sha256': hashlib.sha256(project.read_bytes()).hexdigest(),
                             'iron_farm_is_historical_record_not_live_survey': True}}
    result['snapshot_sha256'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    write(destination, result)
    return result


def codex_binary():
    # Homebrew's JS wrapper may depend on a broken system Node. Prefer its native payload.
    bundled = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex')
    if bundled.is_file():
        return str(bundled)
    payload = Path('/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex')
    return str(payload) if payload.is_file() else shutil.which('codex')


def verify_iteration(root, result):
    """Upstream can finish with every model edit failed and the base retained."""
    summaries = [json.loads(p.read_text()) for p in (root / 'runs').rglob('summary.json')]
    if result.get('failed') or len(summaries) != 1:
        raise RuntimeError('Harness iteration did not complete exactly one task')
    summary = summaries[0]
    mode = summary.get('modes', {}).get('seq', {})
    selection = summary.get('selections', {}).get('seq', {})
    stages = mode.get('stages', [])
    if (len(stages) != 3 or mode.get('fell_back') or not mode.get('ok')
            or any(s.get('fell_back') or s.get('error') for s in stages)
            or not selection.get('ok') or selection.get('fallback')):
        raise RuntimeError('Model edit/composition fell back; upstream task success is not model integration proof')
    for stage in stages:
        calls = list((root / 'codex-audit').glob(stage['label'] + '.a*/answer.json'))
        if not calls:
            raise RuntimeError('Missing actual Codex answer for ' + stage['label'])
    chosen = Path(selection['chosen_run_dir'])
    if root.resolve() not in chosen.resolve().parents:
        raise RuntimeError('Selected deliverable escaped the current run')
    handoff = json.loads((chosen / 'handoff.json').read_text())
    if handoff['live_actions_executed'] != 0:
        raise RuntimeError('Unexpected live action credit')
    write(root / 'adopted-handoff.json', handoff)
    selected_tree = root / 'runs/minecraft-cx-seq1/iron-farm/harnesses' / selection['chosen_label']
    files = {name: (selected_tree / name).read_text() for name in ALLOWED}
    validate_policy(files)
    write(ADOPTED, {'source_run': str(root.resolve()), 'snapshot_sha256': handoff['snapshot_sha256'],
                    'scope': 'diagnostic_check_selection_only_not_game_action_authorization', 'files': files})
    return {'model_iteration_verified': True, 'accepted_edit_stages': len(stages),
            'live_actions_executed': 0, 'selected_handoff': str(chosen / 'handoff.json'),
            'farm_operational_verified': False}


class CodexEditor(Proposer):
    """Current ChatGPT login, read-only CLI, JSON edits applied by an allowlisted host."""
    allowed_paths = ALLOWED
    policy_validator = staticmethod(validate_policy)
    prompt_builder = staticmethod(editor_prompt)

    def call(self, mission, context_dir, label, **kwargs):
        context = Path(context_dir).resolve()
        documents = {str(p.relative_to(context)): p.read_text() for p in context.rglob('*')
                     if p.is_file() and (p.suffix in ('.json', '.md', '.txt') or p.name == 'policy.py') and not p.is_symlink()}
        audit = Path(self.audit_dir) / label
        audit.mkdir(parents=True, exist_ok=True)
        schema = {'type': 'object', 'additionalProperties': False, 'required': ['text', 'files'],
                  'properties': {'text': {'type': 'string'}, 'files': {'type': 'array', 'items': {
                      'type': 'object', 'additionalProperties': False, 'required': ['path', 'content'],
                      'properties': {'path': {'type': 'string', 'enum': sorted(self.allowed_paths)}, 'content': {'type': 'string'}}}}}}
        write(audit / 'schema.json', schema)
        prompt = self.prompt_builder(mission, documents)
        write(audit / 'input.json', {'mission': mission, 'context': documents})
        (audit / 'prompt.txt').write_text(prompt)
        # Preserve the user's configured model, but do not load unrelated MCP servers/hooks.
        config_path = Path.home() / '.codex/config.toml'
        configured = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
        argv = [codex_binary(), 'exec', '--ignore-user-config', '--sandbox', 'read-only', '--ephemeral',
                '--skip-git-repo-check', '--json', '-C', str(audit),
                '--output-schema', str(audit / 'schema.json'), '-o', str(audit / 'answer.json')]
        if configured.get('model'):
            argv += ['--model', configured['model']]
        started = time.monotonic()
        with (audit / 'events.jsonl').open('w') as output, (audit / 'stderr.log').open('w') as errors:
            try:
                env = {k: v for k, v in os.environ.items() if k not in {
                    'OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_ORG_ID', 'OPENAI_PROJECT_ID'}}
                done = subprocess.run(argv + ['-'], input=prompt, text=True, stdout=output, stderr=errors,
                                      timeout=min(kwargs.get('timeout') or 240, 240), check=False, env=env)
            except subprocess.TimeoutExpired as exc:
                raise ProposerError('Codex editor timed out; no automatic retry', attempts=1) from exc
        if done.returncode or not (audit / 'answer.json').exists():
            raise ProposerError(f'Codex editor failed; inspect {audit}', attempts=1)
        answer = json.loads((audit / 'answer.json').read_text())
        workspace = context / 'harness'
        if answer['files']:
            files = {row['path']: row['content'] for row in answer['files']}
            if len(files) != len(answer['files']):
                raise ValueError('Duplicate edited paths')
            self.policy_validator(files)
            for name, content in files.items():
                target = workspace / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or workspace.resolve() not in target.resolve().parents:
                    raise ValueError('Edit escaped isolated harness')
                target.write_text(content)
        reply = Reply(label=label, text=answer['text'], ok=True, attempts=1,
                      workspace=workspace if workspace.exists() else None, audit=audit,
                      channel='codex_cli_chatgpt', wall_s=time.monotonic() - started)
        self._calls.append(reply)
        return reply


class MinecraftAdapter:
    def __init__(self, root, snapshot, task_prompt=None):
        self.root = root.resolve()
        self.substrate = CodexSubstrate()
        channel = ChannelSpec('opencode', 'local/codex-editor')  # custom Proposer; no OpenCode process
        self.spec = BenchSpec(name='minecraft', runs_root=self.root / 'runs', install_mode='codex_root',
                              prompts=BenchPrompts(work='prepare an evidence-grounded Minecraft iron farm continuation handoff'),
                              channels={'proposer': channel, 'selector': channel}, allow_subagents=False)
        source = self.task_files('iron-farm')
        source.mkdir(parents=True, exist_ok=True)
        prompt_path = source / 'task.txt'
        task_prompt = task_prompt or DEFAULT_TASK
        if prompt_path.exists() and prompt_path.read_text() != task_prompt:
            raise ValueError('Task prompt changed; use a new run directory')
        prompt_path.write_text(task_prompt)
        target = source / 'snapshot.json'
        if target.exists() and target.read_bytes() != snapshot.read_bytes():
            raise ValueError('Existing run has a different immutable snapshot; use a new output directory')
        if not target.exists():
            shutil.copyfile(snapshot, target)
        if not self.base_harness().exists():
            files = {'AGENTS.md': RULES, 'scripts/policy.py': 'CHECKS = ["live_state"]\n'}
            if ADOPTED.exists():
                files = json.loads(ADOPTED.read_text())['files']
                validate_policy(files)
            tree.write_tree(self.substrate.surface(), files, self.base_harness(), stubs=False)

    def tasks(self, split='all'): return ['iron-farm']
    def domain_of(self, task_id): return 'minecraft'
    def task_prompt(self, task_id):
        return (self.task_files(task_id) / 'task.txt').read_text()
    def task_files(self, task_id): return self.root / 'sources' / task_id
    def base_harness(self): return self.root / 'base'
    def validate_tree(self, files): validate_policy(files)

    def execute(self, task_id, harness_dir, run_id, *, timeout=None):
        harness = harness_dir or self.base_harness()
        files = {name: (harness / name).read_text() for name in ALLOWED}
        policy = validate_policy(files)
        evidence = json.loads((self.task_files(task_id) / 'snapshot.json').read_text())
        destination = self.root / 'executions' / run_id
        if self.root not in destination.resolve().parents:
            raise ValueError('Run ID escaped output root')
        result = assess(evidence, policy['checks'])
        write(destination / 'handoff.json', result)
        (destination / 'trajectory.md').write_text('[ACTION] Read immutable Kit evidence; apply selected diagnostic checks.\n[OBSERVATION]\n' + json.dumps(result, ensure_ascii=False))
        return destination

    def delivered(self, run_dir): return (run_dir / 'handoff.json').exists()
    def trajectory(self, run_dir, *, obs_trunc): return (run_dir / 'trajectory.md').read_text()
    def deliverable_text(self, run_dir): return (run_dir / 'handoff.json').read_text()
    def deliverable_files(self, run_dir): return {'handoff.json': self.deliverable_text(run_dir)}


def main():
    parser = argparse.ArgumentParser(__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    cap = sub.add_parser('capture')
    cap.add_argument('--output', type=Path, required=True)
    cap.add_argument('--game-root', type=Path, default=Path('/Applications/.minecraft/versions/26.2/config/twob2tkit/automation'))
    cap.add_argument('--project', type=Path, default=KIT / 'work/village-trading-20261017/project-state.json')
    run = sub.add_parser('run')
    run.add_argument('--snapshot', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--prompt-file', type=Path, help='UTF-8 user task prompt; does not override fixed execution boundaries')
    run.add_argument('--allow-snapshot-upload', action='store_true',
                     help='Explicitly authorize sending this snapshot to the signed-in Codex/ChatGPT service')
    probe = sub.add_parser('probe', help='Local diagnostic checks only; no Codex/model call')
    probe.add_argument('--snapshot', type=Path, required=True)
    probe.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'capture':
        capture(args.game_root, args.project, args.output)
        print('Captured Kit evidence without game input:', args.output)
    elif args.command == 'probe':
        write(args.output, assess(json.loads(args.snapshot.read_text()), sorted(CHECKS)))
        print('Local evidence handoff:', args.output)
    else:
        if not args.allow_snapshot_upload:
            parser.error('Run requires explicit snapshot-upload authorization; use probe for local checks')
        adapter = MinecraftAdapter(args.output, args.snapshot, args.prompt_file.read_text() if args.prompt_file else None)
        proposer = CodexEditor(adapter.spec.channels['proposer'], audit_dir=adapter.root / 'codex-audit', attempts=1)
        result = run_domain('minecraft', ['iron-farm'], 1, adapter=adapter, prop=proposer,
                            runs_root=adapter.spec.runs_root, library_root=adapter.root / 'project-library', modes=('seq',))
        write(adapter.root / 'deployment-result.json', result)
        try:
            validation = verify_iteration(adapter.root, result)
        except RuntimeError as exc:
            write(adapter.root / 'integration-validation.json', {'model_iteration_verified': False, 'error': str(exc)})
            raise
        write(adapter.root / 'integration-validation.json', validation)
        print(json.dumps(result, ensure_ascii=False))
        return int(result['failed'] > 0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Window coordination only: preserve exact finals through the frozen sealer."""
import datetime
import hashlib
import json
import pathlib
import re
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[5]
output = root / 'data/eval/m4/gpt6-luna-repeat'
temporal = output / 'temporal'
sessions = pathlib.Path(sys.argv[1])
prep = json.loads((temporal / 'run-preparation.json').read_text(encoding='utf-8'))
tasks = {t['ordinal']: t for t in prep['tasks']}
ledger_path = temporal / 'r1.6-captures.json'
ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {
    'schema_version': 'r1.6-temporal-captures-v1', 'captures': [],
    'preparation_sha256': json.loads((temporal / 'preparation-receipt.json').read_text(encoding='utf-8'))['preparation_sha256']}
captured = {c['ordinal'] for c in ledger['captures']}

def write(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(path)

changed = []
for session in sorted(sessions.glob('*.jsonl')):
    with session.open(encoding='utf-8') as stream:
        first = json.loads(stream.readline())
    source = first['payload'].get('source', {})
    if not isinstance(source, dict):
        continue
    name = source.get('subagent', {}).get('thread_spawn', {}).get('agent_path', '')
    match = re.fullmatch(r'/root/r16_temporal_(\d{3})', name)
    if not match:
        continue
    ordinal = int(match[1])
    if ordinal in captured:
        continue
    task = tasks[ordinal]
    rows = [json.loads(line) for line in session.read_text(encoding='utf-8').splitlines()]
    final = next((row['payload']['content'][0]['text'] for row in reversed(rows)
                  if row.get('payload', {}).get('phase') == 'final_answer'), None)
    if final is None:
        continue
    digest = hashlib.sha256(final.encode('utf-8')).hexdigest()
    if (temporal / 'rejected-finals' / f'{ordinal:03d}-{digest}.json').exists():
        continue
    result = subprocess.run([sys.executable, str(root / 'scripts/seal_config4_temporal_session.py'),
                             '--output', str(output), '--ordinal', str(ordinal), '--session', str(session)],
                            cwd=root, capture_output=True, text=True, encoding='utf-8', check=False)
    if result.returncode:
        changed.append({'ordinal': ordinal, 'status': 'CAPTURE_REJECTED',
                        'final_sha256': digest, 'error': result.stderr[-2400:]})
        continue
    receipt = json.loads(result.stdout)
    if receipt['ordinal'] != ordinal or receipt['task_key'] != task['task_key'] or receipt['final_sha256'] != digest:
        raise RuntimeError('Frozen sealer receipt identity differs')
    capture = {**receipt, 'task_name': name, 'session_file': session.name,
               'session_sha256': hashlib.sha256(session.read_bytes()).hexdigest(),
               'provider_resource_telemetry': 'not_recorded'}
    ledger['captures'].append(capture)
    captured.add(ordinal)
    write(ledger_path, ledger)
    changed.append(capture)

state = {'schema_version': 'r1.6-temporal-checkpoint-v1',
         'updated_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'preparation_sha256': ledger['preparation_sha256'],
         'sealed_temporal_tasks': len(captured), 'pending_temporal_tasks': 40-len(captured),
         'pending_tasks': [tasks[n] for n in sorted(tasks) if n not in captured],
         'status': 'SEALED_REPLAY_AUDIT_PENDING' if len(captured)==40 else 'IN_PROGRESS'}
write(temporal / 'r1.6-checkpoint.json', state)
window_path = output / 'diagnostics/r1.6-window.json'
window = json.loads(window_path.read_text(encoding='utf-8'))
window.update({key: state[key] for key in ('sealed_temporal_tasks', 'pending_temporal_tasks')})
write(window_path, window)
for filename in ('STATUS.md', 'FLAGS.md'):
    path = root / filename
    value = path.read_text(encoding='utf-8')
    value = re.sub(r'\b\d+/40 sealed sides\b', f'{len(captured)}/40 sealed sides', value)
    path.write_text(value, encoding='utf-8', newline='\n')
print(json.dumps({'new_results': changed, 'sealed_temporal_tasks': len(captured),
                  'pending_temporal_tasks': 40-len(captured), 'status': state['status']}, indent=2))

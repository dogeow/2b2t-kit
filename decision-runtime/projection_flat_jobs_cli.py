"""Plan offline by default; explicitly execute through Kit's material scheduler."""
import argparse
import json
from pathlib import Path

from projection_flat_plan import FlatLayout, next_batch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--automation', type=Path)
    args = parser.parse_args(argv)
    load = lambda path: json.loads(path.read_text())
    if args.execute:
        if not args.request or not args.automation or any((args.model, args.audit, args.snapshot, args.policy)):
            parser.error('--execute requires --request and --automation, without offline inputs')
        from material_jobs_cli import serve
        from projection_flat_backend import create_backend
        result = serve(load(args.request), args.automation, args.out, create_backend)
        return 0 if result['state'] in ('completed', 'paused', 'cancelled') else 2
    if not all((args.model, args.audit, args.snapshot, args.policy)) or args.request or args.automation:
        parser.error('Offline planning requires --model --audit --snapshot --policy')
    model, audit = load(args.model), load(args.audit)
    layout = FlatLayout(model.get('projection_model', model), load(args.policy))
    result = next_batch(layout, layout.observed(audit.get('projection_audit', audit)), load(args.snapshot))
    # No imports of the game backend and no live mailbox reads in this mode.
    with args.out.open('x') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(result['operation'], result['phase'])
    return 0 if result['phase'] in ('done', 'ready', 'waiting') else 2


if __name__ == '__main__':
    raise SystemExit(main())

"""Local persistent Kit farm worker. This command never invokes a model or reconnects."""
import argparse
import json
from pathlib import Path
from farm_caretaker import Caretaker

DEFAULT_GAME = Path('/Applications/.minecraft/versions/26.1.2')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, default=DEFAULT_GAME)
    parser.add_argument('--profile', type=Path, required=True,
                        help='Authorized local profile; defaults: 300s, 20 adults per type, 4 seed potatoes, 8 cooked food')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--acknowledge-unknown-outcome', action='store_true',
                        help='Explicitly confirm checked item safety and accept that the original result remains unknown')
    parser.add_argument('--expected-pending-sha256', help='Reject if the original journal changed after the confirmation preview')
    parser.add_argument('action', choices=('run','pause','stop','status','resume','inspect-pending','archive-pending'))
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text())
        if args.action == 'archive-pending':
            from farm_caretaker_archive import archive_pending
            result = archive_pending(args.game_dir/'config/twob2tkit/automation',profile,args.out,
                acknowledge_unknown_outcome=args.acknowledge_unknown_outcome,
                expected_pending_sha256=args.expected_pending_sha256)
            print(json.dumps(result,ensure_ascii=False))
            return 0
        if args.acknowledge_unknown_outcome or args.expected_pending_sha256:
            raise ValueError('归档确认参数只能用于 archive-pending；开始或恢复不会自动归档')
        if args.action == 'inspect-pending':
            from farm_caretaker_review import inspect_pending
            result = inspect_pending(args.game_dir/'config/twob2tkit/automation', profile, args.out)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        caretaker = Caretaker(args.game_dir/'config/twob2tkit/automation', profile, args.out)
        if args.action == 'status':
            result = caretaker.status()
            result['worker_running'] = bool(caretaker.worker_running())
        elif args.action in ('pause','stop'):
            result = {'phase':'submitted', **caretaker.command(args.action)}
        else:
            # Explicit run/resume can reactivate a disabled schedule only after
            # fresh lock/world/control checks. An unresolved intent remains locked.
            if args.action == 'resume' and caretaker.worker_running():
                result={'phase':'submitted',**caretaker.command('resume')}
            else:
                result = caretaker.run(resume=args.action=='resume')
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (RuntimeError,ValueError,OSError,KeyError) as error:
        print(json.dumps({'phase':'waiting','code':'WAIT_CONTROL','detail':str(error),'ai_calls':0},ensure_ascii=False))
        return 2


if __name__ == '__main__': raise SystemExit(main())

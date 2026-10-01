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
    parser.add_argument('action', choices=('run','pause','stop','status','resume'))
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text())
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

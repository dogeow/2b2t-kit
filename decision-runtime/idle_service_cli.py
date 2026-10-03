"""Local idle service CLI; run explicitly, never reconnect or unlock protection."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from farm_caretaker import validate_profile as validate_caretaker
from idle_service import IdleService,default_profile,read,validate_profile
from kit_runtime.journal import write_json

DEFAULT_GAME=Path('/Applications/.minecraft/versions/26.1.2')


def load_profile(path):
    value=read(path)
    for name in ('caretaker_profile',):
        if value.get(name):value[name]=str((path.parent/value[name]).resolve())
    value['plant_registries']=[str((path.parent/p).resolve()) for p in value.get('plant_registries',[])]
    return validate_profile(value)


def running(path):
    if not path.is_file():return False
    with path.open('rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        fcntl.flock(lock,fcntl.LOCK_UN);return False


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,default=DEFAULT_GAME)
    parser.add_argument('--profile',type=Path)
    parser.add_argument('--caretaker-profile',type=Path)
    parser.add_argument('--plant-registry',type=Path,action='append',default=[])
    parser.add_argument('--acknowledge-existing-fields',action='store_true')
    parser.add_argument('action',choices=('template','init','run','status','pause','stop','resume','revalidate-fields'))
    args=parser.parse_args(argv)
    try:
        root=args.game_dir/'config/twob2tkit/automation'
        path=args.profile or root.parent/'idle-service-profile.json'
        if args.action=='template':print(json.dumps(default_profile(),ensure_ascii=False,indent=2));return 0
        if args.action=='init':
            if path.exists():raise RuntimeError('Idle profile already exists; edit the registered file explicitly')
            farm_path=(args.caretaker_profile or root.parent/'farm-caretaker-profile.json').resolve()
            farm=validate_caretaker(read(farm_path));key=hashlib.sha256((farm['server']+'|'+farm['dimension']).encode()).hexdigest()[:20]
            if read(root/'farm-caretakers'/key/'registry.json').get('profile')!=farm:raise RuntimeError('Default idle profile requires the existing explicit farm registration')
            profile=default_profile(str(farm_path));profile.update(authorized=True,server=farm['server'],dimension=farm['dimension'])
            profile['plant_registries']=[str(p.resolve()) for p in args.plant_registry]
            for registry in profile['plant_registries']:
                value=read(registry);scope=value.get('scope') or {}
                if scope.get('server')!=farm['server'] or scope.get('dimension')!=farm['dimension'] or not Path(registry).is_relative_to((root/'farms').resolve()):raise RuntimeError('Planting registry is not an existing field in the farm scope')
            path.parent.mkdir(parents=True,exist_ok=True);write_json(path,validate_profile(profile))
            print(json.dumps({'phase':'configured','profile':str(path),'worker_started':False,'fishing_enabled':False,'adult_keep':farm['adult_keep'],'ai_calls':0},ensure_ascii=False));return 0
        profile=load_profile(path);key=hashlib.sha256((profile['server']+'|'+profile['dimension']).encode()).hexdigest()[:20]
        home=root/'idle-services'/key;book_path=home/'service.json'
        if args.action=='revalidate-fields':
            from idle_field_revalidation import revalidate_fields
            result=revalidate_fields(root,profile,acknowledge_existing_fields=args.acknowledge_existing_fields)
            print(json.dumps(result,ensure_ascii=False));return 0
        if args.action=='status':
            result=read(book_path) if book_path.exists() else {'phase':'not_started','ai_calls':0}
            result['worker_running']=running(home/'worker.lock')
        else:
            service=IdleService(root,profile)
            if args.action in ('pause','stop') or args.action=='resume' and running(service.lock_path):
                result={'phase':'submitted',**service.command(args.action)}
            else:result=service.run()
        print(json.dumps(result,ensure_ascii=False));return 0
    except (RuntimeError,ValueError,OSError,KeyError) as error:
        print(json.dumps({'phase':'waiting','code':'WAIT_IDLE_SERVICE','detail':str(error),'ai_calls':0},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())

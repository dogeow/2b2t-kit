"""Native Kit launcher entry point for deterministic material jobs; no AI provider."""
import argparse
import importlib
import json
from pathlib import Path
import time

from material_jobs import MaterialJob, JobBlocked, JobCancelled, JobPaused
from safety_interlock import require_unlocked


def serve(request, automation, out, factory, *, poll_seconds=.5, max_pause_seconds=86400):
    job = MaterialJob(request, out)
    if job.state.get('terminal'):
        return job.state
    while True:
        if job.state['state'] == 'paused':
            job.backend = None
            paused_at = time.monotonic()
            while True:
                if time.monotonic() - paused_at > max_pause_seconds:
                    return job._write('blocked', '暂停时间已到', '进度已保留；请从 Kit 重新创建继续任务', terminal=True)
                try:
                    action = job.control()
                except JobPaused:
                    action = None
                except JobBlocked as error:
                    return job._write('blocked', '世界已变化', str(error), terminal=True)
                if action == 'cancel':
                    return job._write('cancelled', '已取消', '用户取消任务', terminal=True)
                if action == 'resume':
                    job.resuming = True
                    job._write('queued', '重新核对当前世界', terminal=False)
                    break
                time.sleep(poll_seconds)
        try:
            require_unlocked(automation)
            factory_request = {**job.request, 'context': dict(job.context), '_resume': job.resuming,
                               '_context_not_before':max(job.request['created_at'],job.last_control)}
            job.backend = factory(request=factory_request, automation=Path(automation),
                                  out=Path(out), checkpoint=job.checkpoint)
            result = job.run()
        except (JobPaused, JobCancelled) as error:
            result = job._write('cancelled' if isinstance(error, JobCancelled) else 'paused', '已取消' if isinstance(error, JobCancelled) else '等待继续',
                                str(error), terminal=isinstance(error, JobCancelled))
        except Exception as error:
            result = job._write('blocked', '无法开始', str(error), terminal=True)
        if result.get('terminal'):
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--automation', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    try:
        factory = importlib.import_module('material_jobs_backend').create_backend
    except (ImportError, AttributeError) as error:
        job = MaterialJob(request, args.out)
        job._write('blocked', '后端尚未接入', str(error), terminal=True)
        return 2
    result = serve(request, args.automation, args.out, factory)
    return 0 if result['state'] in ('completed', 'paused', 'cancelled') else 2


if __name__ == '__main__':
    raise SystemExit(main())

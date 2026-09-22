"""Run owned-resource cleanup before ending the native safety lease."""
import json

def register(client,key,callback):
    if not hasattr(client,'resource_cleanup'):client.resource_cleanup={}
    client.resource_cleanup[key]=callback

def complete(client,key):
    getattr(client,'resource_cleanup',{}).pop(key,None)

def run(client):
    failures=[]
    for key,callback in list(getattr(client,'resource_cleanup',{}).items()):
        try:callback()
        except Exception as e:failures.append({'resource':key,'error':str(e),'completed':False})
        else:complete(client,key)
    if failures:
        try:(client.out/'unfinished-resource-cleanup.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2))
        except OSError:pass
        print('RESOURCE_CLEANUP_INCOMPLETE',failures,flush=True)
    return failures

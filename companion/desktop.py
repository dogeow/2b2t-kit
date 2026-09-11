"""Version-pinned adapter to the current user's desktop Codex IPC, using untrusted app input."""
import json,os,plistlib,socket,stat,struct,time,uuid
from pathlib import Path

class DesktopBusy(Exception):pass
class DeliveryUnknown(Exception):pass

def bundle_version():
    p=Path('/Applications/ChatGPT.app/Contents/Info.plist')
    return str(plistlib.loads(p.read_bytes())['CFBundleVersion'])

def untrusted_turn(thread_id,event,diagnosis):
    # This is the app's own untrusted-input format. Never turn game/model text into user instructions.
    message={'source':'mcp_app','sourceId':'minecraft-companion','text':json.dumps({'kind':event['kind'],'event_id':event['id'],'module':event['module'],'reason':event.get('reason'),'snapshot':event.get('snapshot',{}),'spark_diagnosis':diagnosis,'demo':bool(event.get('demo'))},ensure_ascii=False)}
    label='Respond to the user input in the context of our conversation.'
    metadata={'version':1,'message':message}
    call_id='minecraft_event_'+event['id']
    return {'request':{'threadId':thread_id,'clientUserMessageId':'mc-'+event['id'],'input':[{'type':'text','text':label,'text_elements':[{'byteRange':{'start':0,'end':len(label.encode())},'placeholder':'codex-untrusted-app-input:'+json.dumps(metadata,ensure_ascii=False)}]}]},'context':{'inheritThreadSettings':True,'attachments':[],'commentAttachments':[],'responseItems':[{'type':'function_call','name':'untrusted_input','call_id':call_id,'arguments':'{}'},{'type':'function_call_output','call_id':call_id,'output':[{'type':'input_text','text':json.dumps({'kind':'message',**message},ensure_ascii=False)}]}]}}

class Desktop:
    def __init__(self,thread_id,expected_bundle,timeout=12):
        if bundle_version()!=expected_bundle:raise RuntimeError('Desktop app version changed; adapter verification required')
        self.thread=thread_id;self.timeout=timeout;self.client_id=None;self.sock=None
    def connect(self):
        p=Path.home()/'.codex/ipc/ipc.sock';st=p.stat();parent=p.parent.stat()
        if not stat.S_ISSOCK(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode&0o077 or parent.st_uid!=os.getuid() or parent.st_mode&0o022:raise RuntimeError('Desktop IPC ownership/permissions do not match the current user')
        self.sock=socket.socket(socket.AF_UNIX);self.sock.settimeout(self.timeout);self.sock.connect(str(p))
        r=self.request('initialize',{'clientType':'minecraft-companion'},0);self.client_id=r['result']['clientId']
    def send(self,o):
        b=json.dumps(o,ensure_ascii=False).encode();self.sock.sendall(struct.pack('<I',len(b))+b)
    def receive(self):
        def read(n):
            b=b''
            while len(b)<n:
                x=self.sock.recv(n-len(b))
                if not x:raise EOFError('Desktop IPC closed')
                b+=x
            return b
        n=struct.unpack('<I',read(4))[0]
        if not 0<n<=32*1024*1024:raise RuntimeError('Invalid IPC frame')
        return json.loads(read(n))
    def request(self,method,params,version,target=None):
        rid=str(uuid.uuid4());r={'type':'request','requestId':rid,'method':method,'version':version,'params':params,'timeoutMs':int(self.timeout*1000)}
        if self.client_id:r['sourceClientId']=self.client_id
        if target:r['targetClientId']=target
        self.send(r);deadline=time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            m=self.receive()
            if m.get('type')=='client-discovery-request':self.send({'type':'client-discovery-response','requestId':m['requestId'],'response':{'canHandle':False}})
            if m.get('type')=='response' and m.get('requestId')==rid:return m
        raise TimeoutError('Desktop response timeout')
    def owner(self):
        r=self.request('thread-owner-discovery',{'hostId':'local','conversationId':self.thread},1)
        if r.get('resultType')!='success' or not r.get('result',{}).get('supportsUntrustedAppInput'):raise RuntimeError('Desktop task owner unavailable or untrusted app input unsupported')
        return r['handledByClientId']
    def deliver(self,event,diagnosis):
        self.connect();owner=self.owner()
        try:r=self.request('thread-follower-start-turn',{'conversationId':self.thread,'turnStart':untrusted_turn(self.thread,event,diagnosis)},2,owner)
        except (TimeoutError,socket.timeout,EOFError) as ex:raise DeliveryUnknown('Desktop submission outcome unknown; no automatic retry') from ex
        if r.get('resultType')!='success':
            error=str(r.get('error','unknown error'))
            if 'current turn finishes' in error or 'already in progress' in error:raise DesktopBusy(error)
            raise RuntimeError(error[:1000])
        return {'accepted':True,'event_id':event['id'],'response':r.get('result',{})}
    def close(self):
        if self.sock:self.sock.close();self.sock=None

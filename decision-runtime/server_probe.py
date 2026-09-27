"""Read-only Minecraft status probe, cached for fifteen minutes; never logs in."""
import argparse,fcntl,json,socket,struct,time,zipfile
from safety_interlock import require_assistant_control_allowed
from pathlib import Path

INTERVAL_MS=15*60*1000
MAX_PACKET=1_048_576
DEFAULT_STATE=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation/server-probe-simpcraft.json')
DEFAULT_JAR=Path('/Applications/.minecraft/versions/26.1.2/26.1.2.jar')


def varint(value):
    value &= 0xffffffff;data=bytearray()
    while True:
        byte=value&0x7f;value>>=7;data.append(byte|(0x80 if value else 0))
        if not value:return bytes(data)


def read_exact(connection,size,deadline):
    if not 0<=size<=MAX_PACKET:raise ValueError('Status packet exceeds size limit')
    data=bytearray()
    while len(data)<size:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Status response deadline reached')
        connection.settimeout(min(remaining,3));part=connection.recv(size-len(data))
        if not part:raise ConnectionError('Peer closed before sending a complete status response')
        data.extend(part)
    return bytes(data)


def read_varint(connection,deadline):
    value=0
    for n in range(5):
        byte=read_exact(connection,1,deadline)[0]
        if n==4 and byte&0xf0:raise ValueError('Oversized status integer')
        value|=(byte&0x7f)<<(7*n)
        if not byte&0x80:return value
    raise ValueError('Unterminated status integer')


def decode_varint(data,offset=0):
    value=0
    for n in range(5):
        if offset>=len(data):raise ValueError('Truncated status integer')
        byte=data[offset];offset+=1
        if n==4 and byte&0xf0:raise ValueError('Oversized status integer')
        value|=(byte&0x7f)<<(7*n)
        if not byte&0x80:return value,offset
    raise ValueError('Unterminated status integer')


def protocol(jar):
    with zipfile.ZipFile(jar) as z:return int(json.loads(z.read('version.json'))['protocol_version'])


def probe(host='simpcraft.com',port=25565,protocol_version=775):
    if not host or len(host)>255 or not 1<=port<=65535:raise ValueError('Invalid Minecraft endpoint')
    started=time.monotonic();deadline=started+8
    result={'host':host,'port':port,'observed_at':int(time.time()*1000),'login_tested':False}
    try:
        name=host.encode('utf8');handshake=b'\x00'+varint(protocol_version)+varint(len(name))+name+struct.pack('>H',port)+b'\x01'
        with socket.create_connection((host,port),timeout=3) as connection:
            connection.sendall(varint(len(handshake))+handshake+b'\x01\x00')
            length=read_varint(connection,deadline)
            payload=read_exact(connection,length,deadline)
        packet_id,offset=decode_varint(payload)
        text_size,offset=decode_varint(payload,offset)
        if packet_id!=0 or text_size!=len(payload)-offset:raise ValueError('Unexpected Minecraft status response')
        data=json.loads(payload[offset:].decode('utf8'))
        if not isinstance(data,dict) or not isinstance(data.get('version'),dict) or not isinstance(data.get('players'),dict):
            raise ValueError('Response is not Minecraft server status')
        version=data['version'];players=data['players'];online=players.get('online')
        if not isinstance(online,int) or isinstance(online,bool) or online<0:raise ValueError('Invalid player count')
        result.update(status='responding',players_online=online,version=str(version.get('name',''))[:120],server_protocol=version.get('protocol'))
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as error:
        result.update(status='unreachable_from_this_machine',error_type=type(error).__name__,error=str(error)[:200])
    result['elapsed_ms']=round((time.monotonic()-started)*1000)
    return result


def check(state_file=DEFAULT_STATE,host='simpcraft.com',port=25565,game_jar=DEFAULT_JAR):
    state_file=Path(state_file)
    try:require_assistant_control_allowed(state_file.parent)
    except RuntimeError as error:return {'host':host,'port':port,'status':'suspended_by_user','performed_probe':False,'transition':'unchanged','login_tested':False,'detail':str(error)}
    state_file.parent.mkdir(parents=True,exist_ok=True)
    with state_file.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:previous=json.loads(state_file.read_text())
        except (OSError,ValueError):previous={}
        if not isinstance(previous,dict):previous={}
        now=int(time.time()*1000);last=previous.get('observed_at',0)
        if not isinstance(last,int) or isinstance(last,bool):last=0
        if previous.get('host')==host and previous.get('port')==port and 0<=now-last<INTERVAL_MS:
            return {**previous,'performed_probe':False,'transition':'unchanged','next_check_at':last+INTERVAL_MS}
        current=probe(host,port,protocol(game_jar))
        recovered=(current['status']=='responding' and previous.get('status') not in (None,'responding'))
        current.update(performed_probe=True,transition='recovered' if recovered else 'first_response' if current['status']=='responding' and not previous else 'unchanged',
                       next_check_at=current['observed_at']+INTERVAL_MS)
        temp=state_file.with_suffix('.tmp');temp.write_text(json.dumps(current,ensure_ascii=False,indent=2));temp.replace(state_file)
        return current


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='simpcraft.com');parser.add_argument('--port',type=int,default=25565)
    parser.add_argument('--state',type=Path,default=DEFAULT_STATE);parser.add_argument('--game-jar',type=Path,default=DEFAULT_JAR);args=parser.parse_args()
    print(json.dumps(check(args.state,args.host,args.port,args.game_jar),ensure_ascii=False))

if __name__=='__main__':main()

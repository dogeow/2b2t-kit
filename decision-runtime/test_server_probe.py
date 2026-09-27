import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from server_probe import probe,check,varint,INTERVAL_MS
class Connection:
    def __init__(self,data):self.data=data;self.sent=b''
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def settimeout(self,*args):pass
    def sendall(self,data):self.sent+=data
    def recv(self,n):result=self.data[:1];self.data=self.data[1:];return result
class ServerProbeTest(unittest.TestCase):
    def test_split_response_is_decoded_and_no_login_packet_is_sent(self):
        text=json.dumps({'version':{'name':'26.1.2','protocol':775},'players':{'online':25,'max':1000}}).encode()
        payload=b'\x00'+varint(len(text))+text;c=Connection(varint(len(payload))+payload)
        with patch('server_probe.socket.create_connection',return_value=c):result=probe('localhost')
        self.assertEqual('responding',result['status']);self.assertFalse(result['login_tested']);self.assertEqual(25,result['players_online'])
        self.assertEqual(b'\x10\x00\x87\x06\x09localhost\x63\xdd\x01\x01\x00',c.sent)
    def test_tcp_open_without_status_is_not_reported_as_online(self):
        with patch('server_probe.socket.create_connection',return_value=Connection(b'')):result=probe()
        self.assertEqual('unreachable_from_this_machine',result['status'])
    def test_malformed_or_huge_status_is_rejected(self):
        for response in [b'\xff\xff\xff\xff\x10',varint(2_000_000),b'\x02\x00\x04']:
            with patch('server_probe.socket.create_connection',return_value=Connection(response)):self.assertEqual('unreachable_from_this_machine',probe()['status'])
    def test_fifteen_minute_cache_prevents_duplicate_network_work(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';p.write_text(json.dumps({'host':'simpcraft.com','port':25565,'observed_at':1000,'status':'unreachable_from_this_machine'}))
            with patch('server_probe.time.time',return_value=(1000+INTERVAL_MS-1)/1000),patch('server_probe.probe') as network:
                self.assertFalse(check(p)['performed_probe']);network.assert_not_called()
    def test_only_status_recovery_is_announced_once(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';p.write_text(json.dumps({'host':'simpcraft.com','port':25565,'observed_at':0,'status':'unreachable_from_this_machine'}))
            current={'host':'simpcraft.com','port':25565,'observed_at':INTERVAL_MS+1,'status':'responding','login_tested':False}
            with patch('server_probe.time.time',return_value=(INTERVAL_MS+1)/1000),patch('server_probe.protocol',return_value=775),patch('server_probe.probe',return_value=current):
                self.assertEqual('recovered',check(p)['transition']);self.assertEqual('unchanged',check(p)['transition'])
if __name__=='__main__':unittest.main()

class OfflineInstructionTest(unittest.TestCase):
 def test_explicit_hold_prevents_even_status_network_requests(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'assistant-control-hold.json').write_text('{"active":true}')
   with patch('server_probe.socket.create_connection') as network:
    result=check(root/'probe.json');self.assertEqual('suspended_by_user',result['status']);self.assertFalse(result['performed_probe']);network.assert_not_called()

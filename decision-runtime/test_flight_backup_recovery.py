import tempfile,unittest,struct
from pathlib import Path
from flight_backup_recovery import recover

def text(s):
 b=s.encode();return struct.pack('>H',len(b))+b
def tag(kind,name,value):return bytes([kind])+text(name)+value
def fixture(speed):
 setting=tag(8,'name',text('speed'))+tag(6,'value',struct.pack('>d',speed))+b'\0'
 group=tag(8,'name',text('General'))+tag(9,'settings',b'\x0a'+struct.pack('>i',1)+setting)+b'\0'
 settings=tag(9,'groups',b'\x0a'+struct.pack('>i',1)+group)+b'\0'
 module=tag(8,'name',text('flight'))+tag(1,'active',b'\x01')+tag(10,'settings',settings)+b'\0'
 return b'\x0a\0\0'+tag(9,'modules',b'\x0a'+struct.pack('>i',1)+module)+b'\0'

class FlightBackupRecoveryTest(unittest.TestCase):
 def run_case(self,speed):
  d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);root=Path(d.name);p=root/'meteor-client/modules.nbt';p.parent.mkdir();p.write_bytes(fixture(speed));backup=root/'config/twob2tkit/guard-hover-flight.bak';backup.parent.mkdir(parents=True);backup.write_text('0.1 0.03 0.0')
  return root,p
 def test_only_the_owned_double_changes(self):
  root,p=self.run_case(0.);before=p.read_bytes();r=recover(root,root/'proof',running=lambda:False)
  self.assertTrue(r['changed']);self.assertTrue(r['all_other_settings_identical']);self.assertEqual(fixture(.1),p.read_bytes());self.assertEqual(before,(root/'proof/modules.nbt.before').read_bytes())
 def test_manual_speed_override_is_preserved(self):
  root,p=self.run_case(.37);before=p.read_bytes();r=recover(root,root/'proof',running=lambda:False)
  self.assertFalse(r['changed']);self.assertEqual(before,p.read_bytes())
 def test_running_client_prevents_any_write(self):
  root,p=self.run_case(0.);before=p.read_bytes()
  with self.assertRaisesRegex(RuntimeError,'running'):recover(root,root/'proof',running=lambda:True)
  self.assertEqual(before,p.read_bytes())

if __name__=='__main__':unittest.main()

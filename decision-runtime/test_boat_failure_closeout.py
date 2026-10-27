import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from boat_failure_closeout import closed_failed_trip

class BoatFailureCloseoutTests(unittest.TestCase):
 def test_abort_needs_original_known_done_and_immutable_ground_anchor_evidence(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);journal=root/'tow.json';old=dict(complete=False,world_session='w',uuid='b',pending=dict(op='navigate',request_id='move',target=[1,70,1]));backup=root/'original.json';backup.write_text(json.dumps(old));sha=hashlib.sha256(backup.read_bytes()).hexdigest()
   proof=dict(complete=True,goal_complete=False,classification='known_completed_leg_failed_route_safely_anchored',world_session='w',original_sha256=sha,unconfirmed_native_request_absent=True,player_health=20,original_native_terminal=dict(request_id='move',phase='done',op='navigate',world_session='w',params=dict(target=[1,70,1]),inventory_delta={}),secured_boat=dict(uuid='b',alive=True,on_ground=True,leashed=True,leash_resolved=True,leash_holder=dict(type='minecraft:leash_knot'),passengers=[dict(alive=True,health=20,max_health=20)]))
   path=root/'proof.json';path.write_text(json.dumps(proof));book=dict(complete=False,pending=None,aborted=True,world_session='w',uuid='b',failure_closeout=dict(protocol=1,original_backup=backup.name,original_sha256=sha,proof=path.name,proof_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
   self.assertTrue(closed_failed_trip(book,'w','b',journal))
   for change in ('waiting','wrong_move','airborne','hurt','unknown','world','escape','backup_changed'):
    p,b=copy.deepcopy([proof,book])
    if change=='waiting':p['original_native_terminal']['phase']='waiting'
    if change=='wrong_move':p['original_native_terminal']['request_id']='other'
    if change=='airborne':p['secured_boat']['on_ground']=False
    if change=='hurt':p['secured_boat']['passengers'][0]['health']=19
    if change=='unknown':p['unconfirmed_native_request_absent']=False
    if change=='world':p['world_session']='other'
    if change=='escape':b['failure_closeout']['proof']='../proof.json'
    if change=='backup_changed':backup.write_text('{}')
    path.write_text(json.dumps(p));b['failure_closeout']['proof_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    with self.subTest(change=change):self.assertFalse(closed_failed_trip(b,'w','b',journal))

if __name__=='__main__':unittest.main()

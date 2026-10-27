import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_dry_clay_columns import Fake,block
from material_jobs import home_clay_farm as m
from material_jobs.protocol import JobBlocked
from material_jobs.acquisition import Unavailable


class HomeClayFarmTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.c=Fake(self.root);self.c.pos=[100.5,50.,100.5];self.c.counts['minecraft:mud']=4
        tip=block([100,19,100],'pointed_dripstone',solid=False);tip['state']+='[thickness=tip,vertical_direction=down,waterlogged=false]'
        self.c.blocks={(100,19,100):tip,(100,20,100):block([100,20,100],'dark_oak_planks'),
                       (100,21,100):block([100,21,100],'mud',solid=False)}
        self.profile={'server':'server','dimension':'minecraft:overworld','recipe_jar':'unused.jar',
                      'clay_conversion_farm':{'authorized':True,'positions':[[100,21,100]],
                       'approach':[100.5,45.,100.5],'exit':[102.5,45.,102.5]}}
        def moving(c,p,*a,**kw):c.pos=list(p)
        for name,fn in [('_travel',moving),('move',moving),('settled_state',lambda c,*a,**kw:c.status())]:
            p=patch.object(m,name,side_effect=fn);p.start();self.addCleanup(p.stop)
    def run_farm(self,item='minecraft:clay_ball',target=4):
        return m.run(self.c,self.profile,item,target,self.root/'job',lambda:None)
    def test_only_explicit_owned_bounded_positions_and_paths_are_accepted(self):
        m.validate(self.profile)
        for change in ({'authorized':False},{'positions':[[True,21,100]]},{'positions':[[100,21,100],[100,21,100]]},
                       {'approach':[150,45,100]},{'exit':[200,45,100]}):
            with self.subTest(change=change),self.assertRaises(JobBlocked):
                m.validate({**self.profile,'clay_conversion_farm':{**self.profile['clay_conversion_farm'],**change}})
    def test_pending_mud_waits_without_remote_clay_or_mining(self):
        with patch.object(m,'harvest')as harvest,patch.object(m,'refill')as refill:
            result=self.run_farm()
        self.assertEqual('WAIT_FARM_GROWTH',result['code']);self.assertEqual(0,result['after'])
        self.assertFalse(result['remote_clay_fallback']);self.assertTrue(result['safe_to_leave'])
        harvest.assert_not_called();refill.assert_not_called()
        self.assertEqual(self.profile['clay_conversion_farm']['exit'],self.c.pos)
    def test_actual_clay_is_harvested_and_same_bed_immediately_refilled(self):
        self.c.blocks[(100,21,100)]=block([100,21,100],'clay')
        def harvest(c,pos,*a):
            c.blocks.pop(tuple(pos));c.counts['minecraft:clay_ball']+=4;return {'actual_clay_balls_gained':4}
        def refill(c,pos,*a):
            c.blocks[tuple(pos)]=block(pos,'mud');c.counts['minecraft:mud']-=1;return {'inventory_consumed':1}
        with patch.object(m,'harvest',side_effect=harvest)as h,patch.object(m,'refill',side_effect=refill)as r:
            result=self.run_farm()
        self.assertEqual(('done',4,3),(result['phase'],result['after'],self.c.counts['minecraft:mud']))
        h.assert_called_once();r.assert_called_once();self.assertIn((100,19,100),self.c.blocks)
    def test_empty_bed_uses_carried_dirt_and_registered_water_without_mining_mud(self):
        self.c.blocks.pop((100,21,100));self.c.counts['minecraft:mud']=0
        self.c.counts['minecraft:dirt']=1;self.c.counts['minecraft:glass_bottle']=1
        self.profile['mud_bucket_source']={'authorized':True}
        with patch.object(m,'refill_from_dirt',return_value={'complete':True})as direct,patch.object(m,'refill')as mud:
            result=self.run_farm()
        direct.assert_called_once();mud.assert_not_called();self.assertTrue(result['safe_to_leave'])
    def test_changed_or_missing_tip_is_not_treated_as_conversion_wait(self):
        self.c.blocks.pop((100,19,100))
        with self.assertRaisesRegex(JobBlocked,'support/tip changed'):self.run_farm()
    def test_registered_grass_bed_is_recovered_before_normal_farm_classification(self):
        self.c.blocks[(100,21,100)]=block([100,21,100],'grass_block');self.c.counts['minecraft:glass_bottle']=1
        self.profile['mud_bucket_source']={'authorized':True}
        def recover(c,pos,*args):c.blocks[tuple(pos)]=block(pos,'mud');return {'complete':True,'dirt_net_consumed':0}
        with patch('material_jobs.registered_grass_bed.run',side_effect=recover)as r:
            result=self.run_farm()
        r.assert_called_once();self.assertEqual('WAIT_FARM_GROWTH',result['code'])
        self.assertEqual('recover_registered_grass',json.loads((self.root/'job/home-clay-farm.json').read_text())['receipts'][2]['kind'])
    def test_unconfirmed_harvest_is_retained_without_refill_or_replay(self):
        self.c.blocks[(100,21,100)]=block([100,21,100],'clay')
        with patch.object(m,'harvest',side_effect=JobBlocked('unknown harvest'))as h,patch.object(m,'refill')as r:
            with self.assertRaises(JobBlocked):self.run_farm()
            with self.assertRaisesRegex(JobBlocked,'no replay'):self.run_farm()
        h.assert_called_once();r.assert_not_called()
        self.assertIsNotNone(json.loads((self.root/'job/home-clay-farm.json').read_text())['pending'])
        with self.assertRaisesRegex(JobBlocked,'across jobs'):
            m.run(self.c,self.profile,'minecraft:clay_ball',4,self.root/'new-job',lambda:None)
    def test_farm_priority_precedes_registered_remote_sources(self):
        from material_jobs.colored_sources import acquire
        self.profile['colored_source_regions']=[{'item':'minecraft:clay_ball','authorized':True,
              'min':[1000,19,1000],'max':[1001,21,1001],'dry_columns':{}}]
        with (patch.object(m,'run',return_value={'phase':'waiting','code':'WAIT_FARM_GROWTH'})as local,
              patch('material_jobs.dry_clay_columns.run')as remote):
            result=acquire(self.c,'minecraft:clay_ball',4,self.profile,self.root/'sources',lambda:None)
        self.assertEqual('WAIT_FARM_GROWTH',result['code']);local.assert_called_once();remote.assert_not_called()

    def reconciliation(self,ack=2):
        from kit_runtime.journal import write_json
        pos=[100,21,100];shared=self.root/'shared.json';old=self.root/'harvest.json';new=self.root/'refill.json'
        write_json(shared,{'scope':{'world_session':self.c.world},'pending':{'kind':'harvest','pos':pos}})
        write_json(old,{'world_session':self.c.world,'mud':pos,'pending':True,'request_id':'materials-original',
                        'support':self.c.blocks[(100,20,100)],'tip':self.c.blocks[(100,19,100)]})
        write_json(new,{'world_session':self.c.world,'mud':pos,'pending':False,'support_preserved':True,'tip_preserved':True,
                        'inventory_before':11,'inventory_after':10})
        write_json(self.root/'reply-materials-original.json',{'id':'materials-original','op':'mine_block','phase':'done',
                   'world_session':self.c.world,'mining_target':pos,'server_confirmed':True,
                   'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
                   'native_sequence':2,'server_ack_sequence':ack})
        return shared,old,new

    def test_confirmed_old_removal_is_retired_after_distinct_refill_without_output_credit(self):
        shared,old,new=self.reconciliation();original=old.read_bytes()
        result=m.reconcile_confirmed_refill(self.c,shared,old,new,self.root/'resolution.json',lambda:None)
        self.assertEqual(0,result['old_output_credit']);self.assertTrue(result['old_output_collection_unproved'])
        self.assertIsNone(json.loads(shared.read_text())['pending']);self.assertEqual(original,old.read_bytes())
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.calls))
    def test_proved_direct_dirt_refill_can_retire_known_old_removal_without_credit(self):
        shared,old,new=self.reconciliation();pos=[100,21,100]
        new.write_text(json.dumps({'world_session':self.c.world,'pos':pos,'pending':None,'complete':True,
             'dirt_consumed':1,'known_owned_dirt_resumed':False,'support_preserved':True,'tip_preserved':True,
             'receipts':[{'kind':'place_dirt','request_id':'materials-new-dirt'},{'kind':'water_to_mud','request_id':'materials-new-water'}]}))
        result=m.reconcile_confirmed_refill(self.c,shared,old,new,self.root/'resolution.json',lambda:None)
        self.assertEqual(0,result['old_output_credit']);self.assertFalse(result['mining_replayed'])

    def test_distinct_refill_cannot_retire_unknown_original_mining(self):
        shared,old,new=self.reconciliation(ack=1)
        with self.assertRaisesRegex(JobBlocked,'Unknown original mining'):
            m.reconcile_confirmed_refill(self.c,shared,old,new,self.root/'resolution.json',lambda:None)
        self.assertIsNotNone(json.loads(shared.read_text())['pending'])
    def rejected_refill(self):
        shared,harvest,new=self.reconciliation();pos=[100,21,100]
        h=json.loads(harvest.read_text());h.update(pending=False,actual_clay_balls_gained=4,support_preserved=True,tip_preserved=True,
            mining_receipt=json.loads((self.root/'reply-materials-original.json').read_text()))
        pending={'kind':'direct_refill','pos':pos};farm=self.root/'farm.json'
        farm.write_text(json.dumps({'scope':{'world_session':self.c.world},'pending':pending,
            'receipts':[{'kind':'harvest','pos':pos,'result':h}]}))
        shared.write_text(json.dumps({'scope':{'world_session':self.c.world},'pending':pending}))
        new.write_text(json.dumps({'world_session':self.c.world,'pos':pos,'pending':None,'complete':True,
            'dirt_consumed':1,'known_owned_dirt_resumed':False,'support_preserved':True,'tip_preserved':True,
            'receipts':[{'kind':'place_dirt','request_id':'materials-new-dirt'},{'kind':'water_to_mud','request_id':'materials-new-water'}]}))
        message='Water bottle action requires the current healthy idle guarded material lease'
        refusal={'native':{'id':'materials-refused','phase':'error','world_session':self.c.world,'detail':message},
                 'transaction':{'request_id':'materials-refused','op':'bottle_fill','phase':'error','world_session':self.c.world,'detail':message}}
        return shared,farm,refusal,new
    def test_proved_refill_retires_only_pre_dispatch_bottle_refusal_without_new_credit(self):
        shared,farm,refusal,new=self.rejected_refill();original=farm.read_bytes()
        result=m.reconcile_rejected_refill(self.c,shared,farm,refusal,new,self.root/'resolution.json',lambda:None)
        self.assertFalse(result['original_refill_replayed']);self.assertEqual(0,result['new_harvest_credit'])
        self.assertIsNone(json.loads(shared.read_text())['pending']);self.assertEqual(original,farm.read_bytes())
    def test_unknown_bottle_outcome_never_clears_original_pending_refill(self):
        shared,farm,refusal,new=self.rejected_refill();refusal['native']['phase']='waiting'
        with self.assertRaises(JobBlocked):m.reconcile_rejected_refill(self.c,shared,farm,refusal,new,self.root/'resolution.json',lambda:None)
        self.assertIsNotNone(json.loads(shared.read_text())['pending'])

    def test_confirmed_mining_receipt_is_retained_after_root_reply_is_retired(self):
        shared,old,new=self.reconciliation();reply=self.root/'reply-materials-original.json'
        book=json.loads(old.read_text());book['mining_receipt']=json.loads(reply.read_text());old.write_text(json.dumps(book));reply.unlink()
        result=m.reconcile_confirmed_refill(self.c,shared,old,new,self.root/'resolution.json',lambda:None)
        self.assertEqual(0,result['old_output_credit']);self.assertIsNone(json.loads(shared.read_text())['pending'])

    def restored_bed(self):
        shared,farm,_,_=self.rejected_refill()
        original=json.loads(farm.read_text());h=original['receipts'][0]['result'];h.update(before=0,after=4)
        path=self.root/'material-jobs/material-job-old/pipelines/one/sources/home-clay-farm/home-clay-farm.json'
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(original))
        s=json.loads(shared.read_text());s.update(scope={'world_session':self.c.world,'server':'server','dimension':'minecraft:overworld'},journal=str(path))
        shared.write_text(json.dumps(s))
        worker={'id':'material-job-old','world_session':self.c.world,'state':'blocked','process_alive':False,'occupied':False}
        status=self.c.status
        self.c.status=lambda:{**status(),'time':100,'navigating':False,'material_task':{'occupied':False}}
        return shared,path,worker

    def test_filled_bed_retires_stopped_refill_workflow_preserving_unknown_child_claims(self):
        shared,farm,worker=self.restored_bed();original=farm.read_bytes()
        claim=farm.parent/'unknown-bottle.json';claim.write_text('{"unknown_outcome":true}')
        result=m.reconcile_restored_bed(self.c,shared,farm,worker,self.root/'restored.json',lambda:None)
        self.assertIsNone(json.loads(shared.read_text())['pending']);self.assertEqual(original,farm.read_bytes())
        self.assertEqual('{"unknown_outcome":true}',claim.read_text());self.assertEqual(0,result['new_harvest_credit'])
        self.assertFalse(result['old_refill_outcome_inferred']);self.assertTrue(result['child_journals_and_claims_preserved'])
        self.assertEqual(['scan'],[op for op,_ in self.c.calls])

    def test_restored_bed_rejects_live_foreign_or_unknown_original_worker_and_harvest(self):
        for change in ({'process_alive':True},{'occupied':True},{'state':'gathering'},{'world_session':'other'},{'id':'other'}):
            with self.subTest(change=change):
                shared,farm,worker=self.restored_bed()
                with self.assertRaises(JobBlocked):
                    m.reconcile_restored_bed(self.c,shared,farm,{**worker,**change},self.root/'restored.json',lambda:None)
                self.assertIsNotNone(json.loads(shared.read_text())['pending'])
        shared,farm,worker=self.restored_bed();b=json.loads(farm.read_text())
        b['receipts'][0]['result']['mining_receipt']['server_ack_sequence']=1;farm.write_text(json.dumps(b))
        with self.assertRaises(JobBlocked):m.reconcile_restored_bed(self.c,shared,farm,worker,self.root/'restored.json',lambda:None)
        self.assertIsNotNone(json.loads(shared.read_text())['pending'])

    def test_restored_bed_rejects_empty_bed_or_lost_tip_and_current_manual_takeover(self):
        for fault in('empty','tip','manual'):
            with self.subTest(fault=fault):
                self.setUp();shared,farm,worker=self.restored_bed()
                if fault=='empty':self.c.blocks.pop((100,21,100))
                if fault=='tip':self.c.blocks.pop((100,19,100))
                if fault=='manual':self.c.manual=True
                with self.assertRaises((JobBlocked,Unavailable)):m.reconcile_restored_bed(self.c,shared,farm,worker,self.root/'restored.json',lambda:None)
                self.assertIsNotNone(json.loads(shared.read_text())['pending'])


if __name__=='__main__':unittest.main()

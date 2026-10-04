"""Only explicit same-floor barrel stances may bypass the old source-height gates."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import warehouse_audit_cli as stock
import test_warehouse_stock_exit as fixtures


def profile():
    return {'workbench':[761017,65,797836],
        'workbench_entry':[{'kind':'walk','target':[761015.5,65,797838.5]}],
        'workbench_exit':[{'kind':'walk','target':[761015.5,65,797836.5]}],
        'ground_reach_storage':{'schema':1,'expected_block':'minecraft:barrel','foot_y':65,
            'sources':[[761018,69,z]for z in range(797833,797840)],
            'stances':[{'pos':[761016.5,65,z+.5],'face':'west'}for z in range(797835,797838)]}}


class GroundReachTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.out=Path(temp.name)
        self.core=fixtures.NativeCore(self.out/'root',self.out/'out',server='example.test:25565')
        self.core.state['pos']=[761015.5,65,797838.5]
        self.session=stock._Session(self.core,self.core.status(),{'pending':None},self.core.out)
        (self.core.out/'receipts').mkdir();self.p=profile();self.routes=[]
        for pos in self.p['ground_reach_storage']['sources']:
            self.core.put_chest(pos,[],kind='minecraft:barrel',properties='[facing=west,open=false]')
            above=[pos[0],72,pos[2]]
            self.core.scans[tuple(above)]={'pos':above,'state':'Block{minecraft:oak_planks}',
                'fluid':False,'passable':False,'block_entity':False,'solid':True}
        def route(owner,name):
            self.routes.append((name,deepcopy(self.core.state['pos'])))
            self.core.state['pos']=deepcopy(self.p[name][-1]['target'])
        self.route_patch=patch.object(stock._RegisteredRoute,'route',route)
        self.route_patch.start();self.addCleanup(self.route_patch.stop)
        settled=patch('material_jobs.navigation.settled_state',side_effect=lambda c,*a,**kw:c.status())
        settled.start();self.addCleanup(settled.stop)

    def opened(self,pos):return stock._open_container(self.session,pos,self.core.scans[tuple(pos)]['state'],self.p)

    def test_seven_y69_barrels_use_declared_y65_stances_and_original_entry_exit(self):
        for pos in self.p['ground_reach_storage']['sources']:
            frame=self.opened(pos);self.assertEqual('ChestMenu',frame['menu']['type'])
            evidence=self.session.report['ground_reach_proofs'][-1]
            self.assertFalse(evidence['eye_position_verified']);self.assertFalse(evidence['actual_used_face_verified'])
            self.assertEqual(65,self.core.state['pos'][1]);stock._exit_storage(self.session,self.p)
        self.assertEqual(7,sum(name=='workbench_entry'for name,_ in self.routes))
        self.assertEqual(7,sum(name=='workbench_exit'for name,_ in self.routes))
        self.assertTrue(all(p['target'][1]==65 for op,p in self.core.calls if op=='navigate'))
        self.assertFalse(any(op in ('slot_click','collect_supply','mine_block')for op,_ in self.core.calls))

    def test_config_rejects_unknown_fields_wrong_block_route_floor_and_unlisted_stances(self):
        for kind in ('field','block','row','route','stance','ladder'):
            with self.subTest(kind=kind):
                p=deepcopy(self.p);g=p['ground_reach_storage']
                if kind=='field':g['reach_override']=64
                elif kind=='block':g['expected_block']='minecraft:chest'
                elif kind=='row':g['sources'][0][1]=71
                elif kind=='route':p['workbench_exit'][0]['target'][1]=64
                elif kind=='stance':g['stances'][0]['pos'][1]=69
                else:p['workbench_entry'][0]['kind']='ladder'
                with self.assertRaises((stock.StockBlocked,ValueError)):stock._ground_reach_profile(p)

    def test_y71_y72_no_configuration_or_changed_container_refuse_before_entry(self):
        for y,p in ((71,self.p),(72,self.p),(69,{})):
            with self.subTest(y=y,configured=bool(p)):
                pos=[761018,y,797836];self.core.put_chest(pos,[],kind='minecraft:barrel',properties='[facing=west,open=false]')
                above=[pos[0],y+1,pos[2]];self.core.scans[tuple(above)]={'pos':above,'state':'Block{minecraft:oak_planks}'}
                with self.assertRaises(stock.StockBlocked):stock._open_container(self.session,pos,self.core.scans[tuple(pos)]['state'],p)
        pos=[761018,69,797835]
        with self.assertRaises(stock.StockBlocked):stock._ground_reach(self.p,pos,'Block{minecraft:chest}[facing=south,type=single,waterlogged=false]')
        self.assertEqual([],self.routes)

    def test_ray_obstacle_prevents_native_interact_without_breaking_it(self):
        row={'pos':[761017,68,797835],'state':'Block{minecraft:oak_planks}',
             'fluid':False,'passable':False,'solid':True,'block_entity':False}
        self.core.scans[tuple(row['pos'])]=row
        with self.assertRaisesRegex(stock.StockBlocked,'ray envelope'):self.opened([761018,69,797835])
        self.assertFalse(any(op=='interact'for op,_ in self.core.calls))
        self.assertEqual(row,self.core.scans[tuple(row['pos'])])

    def test_partial_foreign_world_manual_and_unknown_ray_fail_before_interact(self):
        for kind in ('partial','world','manual','unknown'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind=='partial':self.core.scan_changes['scan_cells_read']=0
                elif kind=='world':self.core.scan_changes['world_session']='other'
                elif kind=='manual':self.core.state['manual_movement']=True
                else:self.session.report['pending']={'request_id':'unknown'}
                with self.assertRaises((stock.StockBlocked,RuntimeError)):self.opened([761018,69,797835])
                self.assertFalse(any(op=='interact'for op,_ in self.core.calls))

    def test_native_preuse_error_preserves_actual_ray_proof_and_original_exit(self):
        self.core.response_changes['interact']={'phase':'error','detail':'Target interaction face is occluded or out of reach'}
        with self.assertRaises(stock.StockBlocked):self.opened([761018,69,797835])
        self.assertTrue(self.session.report['ground_reach_proofs'])
        self.assertIsNone(self.session.report['pending'])
        stock._exit_storage(self.session,self.p)
        self.assertEqual('workbench_exit',self.routes[-1][0])

    def test_workbench_below_all_body_to_face_rays_is_not_an_occlusion(self):
        self.assertFalse(stock._ray_cell([761016.5,65,797836.5],[761018.00001,69.5,797836.5],[761017,65,797836]))
        self.assertTrue(stock._ray_cell([761016.5,65,797836.5],[761018.00001,69.5,797836.5],[761017,68,797836]))


if __name__=='__main__':unittest.main()

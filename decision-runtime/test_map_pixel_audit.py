import base64,copy,hashlib,unittest
from map_pixel_audit import expected_flat,compare
from material_jobs.projection_spatial_cache import native_content_hash

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=[]
        for z in range(-1,128):
            for x in range(128):
                item='minecraft:red_terracotta'if(x,z)in((7,5),(127,127))else'minecraft:stone'
                cls.rows.append({'pos':[1000+x,64,2000+z],'state':'Block{'+item+'}','item':item})
        cls.digest=native_content_hash(cls.rows)
        cls.model={'model_schema':1,'bounds':{'min':[1000,64,1999],'max':[1127,64,2127]},
                   'loaded_server_chunks_verified':True,'total':16512,'content_hash':cls.digest,'expected':cls.rows}
        cls.palette={'game_version':'26.2','read_only':True,'flat_brightness_id':1,
                     'source':'actual_current_minecraft_block_registry_and_map_color','states':{
                     'Block{minecraft:stone}':{'map_color_id':11,'normal_u8':45},
                     'Block{minecraft:red_terracotta}':{'map_color_id':52,'normal_u8':209}}}
    def expected(self):return expected_flat(self.model,self.palette,[1000,64,2000],self.digest,'26.2')
    def actual(self,raw):
        return {'map_id':42,'scale':0,'center_x':0,'center_z':0,'geographic_center_verified':False,'colors':{
            'source':'current_loaded_client_map_data','packed_color_count':16384,'width':128,'height':128,
            'packed_color_encoding':'base64-u8','packed_colors':base64.b64encode(raw).decode(),
            'colors_sha256':hashlib.sha256(raw).hexdigest()}}
    def test_north_buffer_is_excluded_and_east_south_order_and_unsigned_pixels_are_exact(self):
        expected=self.expected();raw=base64.b64decode(expected['packed_colors'])
        self.assertEqual(16384,len(raw));self.assertEqual(209,raw[5*128+7]);self.assertEqual(45,raw[7*128+5]);self.assertEqual(209,raw[-1])
        r=compare(expected,self.actual(raw),self.digest)
        self.assertEqual(16384,r['matched_pixels']);self.assertTrue(r['all_pixels_match'])
        self.assertFalse(r['freshness_verified']);self.assertFalse(r['geographic_center_verified']);self.assertFalse(r['full_goal_complete'])
    def test_last_pixel_is_checked_and_wrong_orientation_cannot_pass(self):
        e=self.expected();raw=bytearray(base64.b64decode(e['packed_colors']));raw[-1]=45
        r=compare(e,self.actual(raw),self.digest);self.assertEqual(1,r['mismatched_pixels']);self.assertEqual({'x':127,'z':127,'expected_u8':209,'actual_u8':45},r['mismatch_samples'][0])
        raw=bytearray(base64.b64decode(e['packed_colors']));raw[5*128+7],raw[7*128+5]=raw[7*128+5],raw[5*128+7]
        self.assertEqual(2,compare(e,self.actual(raw),self.digest)['mismatched_pixels'])
    def test_old_version_palette_or_missing_current_state_cannot_supply_expected_pixels(self):
        for change in({'game_version':'26.1.2'},{'states':{}},{'flat_brightness_id':2}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                expected_flat(self.model,{**self.palette,**change},[1000,64,2000],self.digest,'26.2')
    def test_partial_model_wrong_hash_and_absent_north_buffer_are_rejected(self):
        for change in({'expected':self.rows[128:],'total':16384},{'content_hash':'0'*64},
                       {'bounds':{'min':[1000,64,2000],'max':[1127,64,2127]}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                expected_flat({**self.model,**change},self.palette,[1000,64,2000],self.digest,'26.2')
    def test_incomplete_corrupted_and_zoomed_game_maps_are_rejected(self):
        e=self.expected();raw=base64.b64decode(e['packed_colors'])
        for fault in('short','hash','zoom','synthetic'):
            a=self.actual(raw[:-1]if fault=='short'else raw)
            if fault=='hash':a['colors']['colors_sha256']='0'*64
            if fault=='zoom':a['scale']=1
            if fault=='synthetic':a['colors']['source']='generated'
            with self.subTest(fault=fault),self.assertRaises(ValueError):compare(e,a,self.digest)

if __name__=='__main__':unittest.main()

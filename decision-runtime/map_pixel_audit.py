"""Read-only full map-pixel comparison against a pinned flat native projection.

No game action, generated map pixel, cache-freshness claim, or whole-goal completion.
"""
import base64,hashlib
from material_jobs.projection_spatial_cache import native_content_hash


def expected_flat(model,palette,origin,required_hash,game_version):
    if (not isinstance(origin,list)or len(origin)!=3 or any(type(n)is not int for n in origin)):
        raise ValueError('Exact picture origin required')
    x,y,z=origin;low=[x,y,z-1];high=[x+127,y,z+127];rows=model.get('expected')
    if (model.get('model_schema')!=1 or model.get('bounds')!={'min':low,'max':high}
            or model.get('loaded_server_chunks_verified')is not True
            or model.get('content_hash')!=required_hash or model.get('total')!=16512
            or not isinstance(rows,list)or len(rows)!=16512 or native_content_hash(rows)!=required_hash):
        raise ValueError('Complete pinned128x128 picture and128-cell north shading buffer required')
    cells={}
    for row in rows:
        p=tuple(row['pos'])
        if p in cells or len(p)!=3 or any(type(n)is not int for n in p)or not all(a<=n<=b for a,n,b in zip(low,p,high)):
            raise ValueError('Duplicate, nonflat or out-of-range projection cell')
        cells[p]=row['state']
    if (palette.get('game_version')!=game_version or palette.get('read_only')is not True
            or palette.get('flat_brightness_id')!=1
            or palette.get('source')!='actual_current_minecraft_block_registry_and_map_color'):
        raise ValueError('Palette must come from the exact current game registry')
    colors={}
    for state in set(cells.values()):
        row=palette.get('states',{}).get(state)or{};color=row.get('map_color_id');packed=row.get('normal_u8')
        if type(color)is not int or not 1<=color<64 or type(packed)is not int or packed!=color*4+1:
            raise ValueError('Missing or invalid current opaque map color')
        colors[state]=packed
    raw=bytes(colors[cells[(x+dx,y,z+dz)]]for dz in range(128)for dx in range(128))
    return {'schema':1,'model_content_hash':required_hash,'game_version':game_version,'picture_origin':origin,
            'north_shading_buffer_cells':128,'flat_brightness_id':1,'width':128,'height':128,
            'packed_color_encoding':'base64-u8','packed_colors':base64.b64encode(raw).decode(),
            'colors_sha256':hashlib.sha256(raw).hexdigest(),'pixel_order':'index=z*128+x; x east/right, z south/down',
            'source':'expected_pixels_only_not_an_actual_game_map'}


def _bytes(colors):
    if (colors.get('width')!=128 or colors.get('height')!=128 or colors.get('packed_color_encoding')!='base64-u8'):
        raise ValueError('Exact128x128 unsigned map bytes required')
    try:raw=base64.b64decode(colors['packed_colors'],validate=True)
    except (ValueError,KeyError,TypeError)as e:raise ValueError('Invalid packed map bytes')from e
    if len(raw)!=16384 or hashlib.sha256(raw).hexdigest()!=colors.get('colors_sha256'):
        raise ValueError('All16384 map bytes and their exact hash are required')
    return raw


def compare(expected,map_audit,required_hash):
    if expected.get('model_content_hash')!=required_hash:raise ValueError('Expected model hash changed')
    if type(map_audit.get('map_id'))is not int or map_audit['map_id']<0 or map_audit.get('scale')!=0:
        raise ValueError('Actual filled zero-scale map ID required')
    actual=map_audit.get('colors')or{}
    if actual.get('source')!='current_loaded_client_map_data' or actual.get('packed_color_count')!=16384:
        raise ValueError('Actual complete native map-cache pixel result required')
    want,got=_bytes(expected),_bytes(actual)
    wrong=[i for i,(a,b)in enumerate(zip(want,got))if a!=b]
    return {'read_only':True,'map_id':map_audit['map_id'],'model_content_hash':required_hash,
            'matched_pixels':16384-len(wrong),'total_pixels':16384,'mismatched_pixels':len(wrong),
            'all_pixels_match':not wrong,'expected_colors_sha256':expected['colors_sha256'],
            'actual_colors_sha256':actual['colors_sha256'],'actual_none_pixels':sum((v>>2)==0 for v in got),
            'mismatch_samples':[{'x':i%128,'z':i//128,'expected_u8':want[i],'actual_u8':got[i]}for i in wrong[:32]],
            'freshness_verified':False,'geographic_center_verified':False,'full_goal_complete':False}

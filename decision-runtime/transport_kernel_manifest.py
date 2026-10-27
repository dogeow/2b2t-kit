"""Identify the implementation actually imported by the sole village worker."""
import hashlib,marshal
from pathlib import Path
import boat_towing,boat_safety,vehicle_observation

def manifest():
    modules=[boat_towing,boat_safety,vehicle_observation]
    functions=[(boat_towing,n)for n in ['run','envelope','measured_cargo_bounds','clear_rows','next_pilot','finish_known_leg']]
    functions += [(boat_safety,n)for n in ['retreat_plan','return_after_known_move']]+[(vehicle_observation,'read_frame')]
    return dict(protocol=boat_towing.TRANSPORT_GUARD_PROTOCOL,
        loaded_code_sha256={m.__name__+'.'+n:hashlib.sha256(marshal.dumps(getattr(m,n).__code__)).hexdigest()for m,n in functions},
        source_sha256={m.__name__:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()for m in modules},
        module_paths={m.__name__:str(Path(m.__file__).resolve())for m in modules})

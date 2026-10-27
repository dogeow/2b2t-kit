"""Validate the loaded transport kernel before acquiring any native lease."""
from transport_kernel_manifest import manifest

def open_verified_owner(factory,*args,**kwargs):
    transport=manifest()
    if transport.get('protocol')!=2:
        raise RuntimeError('Full passenger transport safety must be verified before opening a material owner')
    return factory(*args,**kwargs),transport

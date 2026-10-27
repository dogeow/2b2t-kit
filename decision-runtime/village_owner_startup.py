"""Validate the loaded transport kernel before acquiring any native lease."""
from transport_kernel_manifest import manifest

def open_verified_owner(factory,*args,**kwargs):
    from harness_runtime import selected
    selected()  # Validate adopted data before any native lease is opened.
    transport=manifest()
    if transport.get('protocol')!=2:
        raise RuntimeError('Full passenger transport safety must be verified before opening a material owner')
    return factory(*args,**kwargs),transport

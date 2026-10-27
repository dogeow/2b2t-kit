"""Count native acknowledged interactions across stations; never infer target completion."""
def acknowledged_delta(before,after):
    a=before.get('professional_printer')or{};b=after.get('professional_printer')or{}
    epoch=a.get('server_confirmed_epoch');first=a.get('server_confirmed_total');last=b.get('server_confirmed_total')
    if (not isinstance(epoch,str)or not epoch or b.get('server_confirmed_epoch')!=epoch
            or not isinstance(before.get('world_session'),str)or not before['world_session']
            or after.get('world_session')!=before['world_session']
            or type(first)is not int or type(last)is not int or first<0 or last<first):
        raise RuntimeError('Native acknowledgement scope changed or cumulative counter is unavailable')
    return last-first

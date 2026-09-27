"""Reconcile interrupted concrete batches from actual stock and cell state; never replay spent powder."""
import time
from shore_concrete import item_count,block_state
SOIL=('Block{minecraft:dirt}','Block{minecraft:grass_block}')


def resolve(rows,pos,expected):
    row=next((r for r in rows if r['pos']==list(pos)),{})
    actual=row.get('state','Block{minecraft:air}')
    if actual==expected:return actual
    if expected.startswith(SOIL) and actual.startswith(SOIL) and row.get('solid') and not row.get('fluid') and not row.get('block_entity'):
        return actual
    raise RuntimeError('Concrete support changed')


def is_soil_stop(result):
    return result.get('phase') in ('waiting','error','stopped') and any(text in str(result.get('detail')) for text in ('支撑面发生变化','Concrete support changed'))


def reconciliable_stop(result):
    return is_soil_stop(result) or (result.get('phase') in ('waiting','error','stopped')
        and any(text in str(result.get('detail')) for text in ('服务器未确认挖除','服务器未确认放置')))


def recover(client,result,before,support,expected,powder,solid,n,prepare=None):
    steps=[];cell=[support[0],support[1]+1,support[2]]
    for _ in range(2):
        if not reconciliable_stop(result):return result,expected
        state=client.status()
        if state.get('health',0)<19 or state.get('guard_busy'):return result,expected
        rows=client.request('scan',min=list(support),max=cell,details=True)['blocks']
        expected=resolve(rows,support,expected)
        # The scan itself can outlast a late inventory packet. Re-observe before accounting.
        state=client.status()
        deadline=time.monotonic()+2
        while (item_count(before,powder)-item_count(state,powder)>item_count(state,solid)-item_count(before,solid)
               and block_state(rows,cell)!=f'Block{{{solid}}}' and time.monotonic()<deadline):
            if state.get('health',0)<19 or state.get('guard_busy'):return result,expected
            time.sleep(.15);state=client.status()
            rows=client.request('scan',min=list(support),max=cell,details=True)['blocks']
            expected=resolve(rows,support,expected)
        # A soil update may interrupt after the server broke the solid but before
        # the native pickup leg. Collect only this batch's fresh exact-size drop.
        deficit=(item_count(before,powder)-item_count(state,powder)
                 -(item_count(state,solid)-item_count(before,solid)))
        if deficit>0 and block_state(rows,cell) in ('Block{minecraft:air}','Block{minecraft:cave_air}'):
            from shore_concrete import batch_pickup_candidate
            from drop_collection import collect_drop
            candidate=batch_pickup_candidate(before,state,solid,cell,deficit)
            if candidate is not None and state.get('health',0)>=19 and not state.get('guard_busy'):
                collect_drop(client,candidate,observation=state,seconds=12)
                state=client.status()
        used=item_count(before,powder)-item_count(state,powder)
        gained=item_count(state,solid)-item_count(before,solid)
        if not 0<=gained<=used<=n:raise RuntimeError('Soil interruption has an ambiguous material balance')
        if used-gained==1 and block_state(rows,cell)==f'Block{{{solid}}}':
            if item_count(state,powder)<1:raise RuntimeError('Keep the residual concrete for the next supplied batch')
            if prepare:prepare(expected)
            client.checked('select_item',item=powder)
            resumed=client.request('concrete_batch',support=list(support),expected_state=expected,powder=powder,target_count=1,seconds=30)
            after=client.status()
            if resumed.get('phase')!='done' or item_count(after,powder)!=item_count(state,powder) or item_count(after,solid)!=item_count(state,solid)+1:
                raise RuntimeError('Residual concrete not verified after natural soil change')
            steps.append({'kind':'recover_existing_solid','count':1});state=after;gained+=1
        if gained!=used:raise RuntimeError('Missing concrete drops are not a soil-state recovery')
        # A zero-consumption timeout is ambiguous, so never resend that placement.
        if used==0 and not is_soil_stop(result):return result,expected
        remaining=n-used
        if remaining:
            latest=client.request('scan',min=cell,max=cell)['blocks']
            if block_state(latest,cell) not in ('Block{minecraft:air}','Block{minecraft:cave_air}') and not block_state(latest,cell).startswith('Block{minecraft:water}'):
                raise RuntimeError('Interrupted cell is not empty after verified pickup')
            if prepare:prepare(expected)
            client.checked('select_item',item=powder)
            result=client.request('concrete_batch',support=list(support),expected_state=expected,powder=powder,target_count=remaining,seconds=120)
            steps.append({'kind':'continue_unspent_powder','count':remaining,'phase':result.get('phase')})
            if reconciliable_stop(result):continue
            state=client.status()
        if item_count(before,powder)-item_count(state,powder)==n and item_count(state,solid)-item_count(before,solid)==n:
            return {'phase':'done','detail':'interrupted concrete batch reconciled; full batch inventory verified','soil_recovery':steps},expected
        return result,expected
    return result,expected

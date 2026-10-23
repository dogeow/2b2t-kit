"""Keep historical missing residents while requiring witnessed replacements."""
def expected_population(previous, keepers, expectation=None, birth_proof=None):
    previous,keepers=set(previous),set(keepers)
    if not previous or not keepers<=previous:raise ValueError('Previous witnessed population and keeper identities required')
    if expectation is None:return previous
    if expectation.get('user_authorized_replacement')is not True or expectation.get('does_not_claim_death')is not True:
        raise ValueError('Explicit replacement history required; no death inference')
    required=expectation.get('must_observe_uuids');history=expectation.get('historical_missing_uuids')
    if (not isinstance(required,list)or not required or len(required)!=len(set(required))
            or not isinstance(history,list)or any(not isinstance(v,str)or not v for v in required+history)):
        raise ValueError('Exact distinct population identities required')
    expected=set(required);retired=previous-expected;added=expected-previous
    if not keepers<=expected or not retired<=set(history)or keepers&set(history):
        raise ValueError('A supplier or unrecorded resident cannot be silently removed')
    if added:
        if not isinstance(birth_proof,dict)or birth_proof.get('newborn_verified')is not True:raise ValueError('New residents require actual birth evidence')
        samples=birth_proof.get('samples',[])
        if len(samples)<2 or samples[-1]['observer_time']<=samples[-2]['observer_time']:raise ValueError('Two fresh birth observations required')
        witnessed=[]
        for sample in samples[-2:]:
            witnessed.append({v['uuid']for v in sample['babies']if v.get('is_baby')is True and v.get('client_health')==20})
        if not added<=witnessed[0]&witnessed[1]:raise ValueError('Replacement identity not witnessed twice')
        if len(added)>len(retired):raise ValueError('Replacement expectation cannot silently expand population')
    return expected

"""Identical fixed novice offers can be a new draw after a fully proved reset."""
def fresh_generation(merchant,previous):
 if previous is None:return True
 sequence=previous.get('native_sequence')
 if(previous.get('pending')is not False or previous.get('station_restored')is not True or type(sequence)is not int or sequence<=0 or previous.get('server_ack_sequence')!=sequence):return False
 if merchant.get('offers_fingerprint')!=previous.get('old_fingerprint'):return True
 return(previous.get('pending')is False and previous.get('station_restored')is True
  and previous.get('unemployment_observed')is True and type(sequence)is int and sequence>0
  and previous.get('server_ack_sequence')==sequence
  and isinstance(merchant.get('opening_request_id'),str)and merchant['opening_request_id']
  and merchant['opening_request_id']!=previous.get('old_opening'))

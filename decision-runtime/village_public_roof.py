"""Select a clear central-aisle roof column; preserve lights and quarantined blocks."""
def choose(rows,x,floor,blocked=(),*,low_x=761017,high_x=761033,aisle_z=797811):
 from public_roof_geometry import choose_clear_roof
 return choose_clear_roof(rows,x,floor,aisle_z,blocked,low_x=low_x,high_x=high_x)

def leave(c,entry,floor,open_roof,close_roof,*,aisle_z=797811):
 if type(aisle_z)is not int or entry[2]!=aisle_z or entry[1]!=floor+3:raise ValueError('Service roof must belong to this explicit aisle')
 s=c.check();c.n('walk',target=[s['pos'][0],float(floor),aisle_z+.5],arrival=.1,restore_flight=False,seconds=20);c.n('walk',target=[entry[0]+.5,float(floor),entry[2]+.5],arrival=.1,restore_flight=False,seconds=20);c.nav([entry[0]+.5,floor+.1,entry[2]+.5]);open_roof(c,entry,'down');c.nav([entry[0]+.5,floor+5.2,entry[2]+.5]);close_roof(c,entry)

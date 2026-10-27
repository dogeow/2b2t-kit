"""Register only a new maximum with a paid, re-opened same-UUID server quote."""
from pathlib import Path
from collections import Counter
import json,re
from villager_trading import book_matches,verify_reopened_lock
from kit_runtime.journal import write_json
LABELS={'minecraft:protection':'保护','minecraft:sharpness':'锋利','minecraft:smite':'亡灵杀手','minecraft:efficiency':'效率','minecraft:punch':'冲击','minecraft:loyalty':'忠诚','minecraft:riptide':'激流','minecraft:blast_protection':'爆炸保护','minecraft:projectile_protection':'弹射物保护','minecraft:quick_charge':'快速装填','minecraft:piercing':'穿透','minecraft:lure':'饵钓'}
def register(base,out,slot,result,quote_result,certificate_name,world):
 base=Path(base);out=Path(out);quote_result=Path(quote_result);p=json.loads((base/'project-state.json').read_text());sel=result['selected'];key=sel['enchantment'];level=sel['level'];uid=slot['occupant_uuid'];group='locked_optional_trades'if key in p['optional_enchantment_targets']else'locked_trades';targets=p['optional_enchantment_targets']if group=='locked_optional_trades'else p['enchantment_targets'];m=result['reopened_merchant']
 if(result.get('complete')is not True or result.get('pending')or result.get('world_session')!=world or result.get('uuid')!=uid
    or result.get('locked')is not True or level!=targets[key]or key in p[group]or m['villager_uuid']!=uid
    or m.get('owned')is not True or not m.get('owner_task')or m['trader_xp']<=0
    or not any(book_matches(o['result'],key,level)for o in m['offers'])
    or json.loads(quote_result.read_text())!=result):raise RuntimeError('New maximum lacks a unique paid same-world immutable server quote')
 verify_reopened_lock(result['purchase'],m)
 cert=out/certificate_name
 if cert.exists():raise RuntimeError('Keeper certificate already exists; do not duplicate registration')
 label=LABELS[key];path=base/'ENCHANTMENT-KEEPERS.md';text=path.read_text();pattern=r'\| '+re.escape(label)+r' \| '+str(level)+r' \| ([^|]+) \| [^|]+ \| [^|]+ \|';text,n=re.subn(pattern,lambda m:f'| {label} | {level} | {m.group(1).strip()} | 已核验锁定 | {slot["id"]} |',text,count=1)
 if n!=1:raise RuntimeError('Unique keeper table row missing; no registration files changed')
 layout=json.loads((base/'layout-plan.json').read_text());row=next(v for v in layout['slots']if v['id']==slot['id'])
 quoted=Counter();paid=Counter()
 for kind in('cost_a','cost_b'):
  value=sel['offer'][kind];quoted[value['item']]+=value['count'];value=result['payment']['offer'][kind];paid[value['item']]+=value['count']
 proof=dict(complete=True,pending=None,open_roofs=[],world_session=world,keeper_uuid=uid,merchant=m,enchantment=key,level=level,slot=slot['id'],immutable_quote_result=str(quote_result.relative_to(base)),book_purchased=result['book_purchased'],actual_lock_payment={k:v for k,v in paid.items()if v})
 p[group][key]=dict(level=level,villager_uuid=uid,server_history_verified=True,trader_xp=m['trader_xp'],proof=str(cert.relative_to(base)),book_purchased=result['book_purchased'],location=slot['id'],workstation_restock_verified=False,cost_emerald=quoted['minecraft:emerald'],cost_book=quoted['minecraft:book'],lock_payment_kind=result['payment']['kind'],actual_lock_payment=proof['actual_lock_payment']);p['confirmed_duplicate_keepers'][key]={'proof':str(cert.relative_to(base))};p['highest_level_enchantments_locked']=len(p['locked_trades']);p['remaining_enchantment_targets']={k:v for k,v in p['enchantment_targets'].items()if k not in p['locked_trades']};p['enchantment_duplicate_policy']['confirmed_required_count']=len(p['locked_trades'])
 row.update(trade_verified=True,locked_enchantment=key,locked_level=level,trade_locked_profession=True,trade_proof=str(cert.relative_to(base)))
 text=re.sub(r'进度：必需\d+/22；顺带\d+/11',f"进度：必需{len(p['locked_trades'])}/22；顺带{len(p['locked_optional_trades'])}/11",text)
 write_json(cert,proof);write_json(base/'project-state.json',p);write_json(base/'layout-plan.json',layout);path.write_text(text);return str(cert.relative_to(base))

package dev.twob2tkit.automation;

/** A sent block use owns only its expected newly opened processing menu. */
final class ProcessingMenuOpening {
 private String request="",expected="";
 private int original=-1,observed=-1,firstTick=-1;
 private boolean cancelled;
 void begin(String id,String type,int originalMenu){
  if(id.isBlank()||!java.util.Set.of("LoomMenu","StonecutterMenu","MerchantMenu").contains(type))throw new IllegalArgumentException("Exact processing open required");
  request=id;expected=type;original=originalMenu;observed=-1;firstTick=-1;cancelled=false;
 }
 boolean pending(String id){return !request.isBlank()&&request.equals(id);}
 boolean observe(String id,String type,int menu,int tick,boolean scope){
  if(!pending(id)||cancelled)return false;
  if(!scope){cancelled=true;return false;}
  boolean matches=expected.equals(type)&&menu>0&&menu!=original;
  if(observed>=0&&(!matches||menu!=observed)){cancelled=true;return false;}
  if(!matches)return false;
  if(observed<0){observed=menu;firstTick=tick;}
  return true;
 }
 boolean ready(String id,int tick){return pending(id)&&!cancelled&&observed>=0&&tick-firstTick>=2;}
 boolean cancelled(String id){return pending(id)&&cancelled;}
}

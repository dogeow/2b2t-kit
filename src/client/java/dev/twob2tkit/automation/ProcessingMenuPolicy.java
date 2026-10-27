package dev.twob2tkit.automation;

/** One ordinary selection; claiming output remains a separate inventory transaction. */
final class ProcessingMenuPolicy {
 private ProcessingMenuPolicy(){}
 static boolean permits(String type,boolean owned,boolean healthy,boolean manual,boolean cursorEmpty,
        int actualMenu,int expectedMenu,int choices,int button,boolean identityMatches){
  return (type.equals("loom")||type.equals("stonecutter"))&&owned&&healthy&&!manual&&cursorEmpty
      &&actualMenu>0&&actualMenu==expectedMenu&&choices>0&&choices<=1024
      &&button>=0&&button<choices&&identityMatches;
 }
}

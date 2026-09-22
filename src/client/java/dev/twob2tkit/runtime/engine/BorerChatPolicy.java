package dev.twob2tkit.runtime.engine;

import java.util.Set;

/** Keep action results and real stop reasons in chat; preparation and strategy live in mining UI. */
final class BorerChatPolicy {
    static String started(String mode){return "已开始"+mode+"，按 B 暂停";}
    static String stopped(String reason,String safety){
        if(reason==null||reason.isBlank())reason="未知原因";
        if(Set.of("离开世界","退出游戏").contains(reason))return null;
        String text=Set.of("按键停止","界面停止","设置页关闭","界面停止当前挖掘任务").contains(reason)?"挖矿已暂停":"挖矿已停止："+reason;
        return text+(safety==null||safety.isBlank()?"":"；"+safety);
    }
}

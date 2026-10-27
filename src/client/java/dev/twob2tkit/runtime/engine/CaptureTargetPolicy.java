package dev.twob2tkit.runtime.engine;

import java.util.UUID;

/** One explicitly selected farm bait. It grants no permission to attack, move, or reconnect. */
final class CaptureTargetPolicy {
    static final String NAME="Kit Iron Farm";
    record Scope(String world,String lease,String task,long revision,String player,
                 UUID target,String type,long issued,long expires) {}
    record Owner(String world,String lease,String task,long revision,String player,long time,
                 boolean materials,boolean guard,boolean pve,boolean manual,boolean held,float health,boolean busy) {}
    static boolean owns(Scope s,Owner h,long now,boolean named){
        return s!=null&&h!=null&&s.target()!=null&&baitType(s.type())
            &&nonempty(s.world())&&nonempty(s.lease())&&nonempty(s.task())&&nonempty(s.player())
            &&s.world().equals(h.world())&&s.lease().equals(h.lease())&&s.task().equals(h.task())
            // Normal material inputs advance the revision while retaining the
            // exact lease. Manual takeover and stop still revoke the owner.
            &&s.revision()<=h.revision()&&s.player().equals(h.player())
            &&h.materials()&&h.guard()&&h.pve()&&!h.manual()&&!h.held()&&h.health()>0
            &&now>=h.time()&&now-h.time()<=1500&&s.issued()<=now
            &&s.expires()>s.issued()&&s.expires()-s.issued()<=60000
            &&(named||h.health()==20&&now<=s.expires());
    }
    static boolean admit(Scope s,Owner h,long now){return owns(s,h,now,false)&&s.revision()==h.revision()&&!h.busy();}
    static boolean baitType(String type){return "minecraft:zombie".equals(type)||"minecraft:drowned".equals(type);}
    static boolean aboardExpectedBoat(UUID expected,UUID actual,boolean riding,boolean ordinaryBoat,boolean alive){
        return expected!=null&&expected.equals(actual)&&riding&&ordinaryBoat&&alive;
    }
    static boolean subject(Scope s,UUID actual,String type,boolean alive,boolean baby,float health,
                           boolean hasName,String name,double distance){
        return s!=null&&s.target()!=null&&baitType(s.type())&&s.target().equals(actual)&&s.type().equals(type)&&alive&&!baby&&health>0
            &&Double.isFinite(distance)&&distance>=0&&distance<=64&&(!hasName||NAME.equals(name));
    }
    static boolean veto(UUID expected,UUID actual,boolean automatic,boolean current,boolean alive){
        return expected!=null&&expected.equals(actual)&&automatic&&current&&alive;
    }
    private static boolean nonempty(String s){return s!=null&&!s.isBlank();}
}

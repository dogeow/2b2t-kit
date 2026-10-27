package dev.twob2tkit.runtime.engine;

import java.util.UUID;

/** One explicit empty receiver may claim one healthy nearby bait before combat reacts. */
final class CaptureReceiverPolicy {
    static boolean claimed(String id,String consumed,String published,boolean durable){
        return id!=null&&!id.isEmpty()&&(durable||id.equals(consumed)
            ||published!=null&&published.startsWith("rx-"+id+"-"));
    }
    record Request(String id,String world,String lease,String task,long revision,String player,UUID boat,long issued,long expires,boolean allowUnleashed) {
        Request(String id,String world,String lease,String task,long revision,String player,UUID boat,long issued,long expires){
            this(id,world,lease,task,revision,player,boat,issued,expires,false);
        }
    }
    static boolean receiverBoat(boolean alive,boolean ordinary,boolean empty,boolean leashed,boolean ownLeash,boolean allowUnleashed){
        return alive&&ordinary&&empty&&(leashed?ownLeash:allowUnleashed);
    }
    static boolean authorized(Request r,CaptureTargetPolicy.Owner o,long now){
        if(r==null||o==null||r.id()==null||!r.id().matches("[A-Za-z0-9_-]{1,16}")||r.boat()==null
                ||r.issued()>now||r.expires()<=now||r.expires()<=r.issued()||r.expires()-r.issued()>600000
                ||r.revision()<1||r.revision()>o.revision())return false;
        var probe=new CaptureTargetPolicy.Scope(r.world(),r.lease(),r.task(),o.revision(),r.player(),r.boat(),
            "minecraft:zombie",now,now+15000);
        // An unrelated fight must not win the race to this exact full-health bait.
        // All world, lease, player-health, manual-control and emergency checks remain.
        return CaptureTargetPolicy.owns(probe,o,now,false);
    }
    static boolean candidate(String type,boolean alive,boolean baby,boolean named,boolean fire,boolean riding,
                             float health,String hand,double boatDistance,double playerDistance,double heightDifference){
        return CaptureTargetPolicy.baitType(type)&&alive&&!baby&&!named&&!fire&&!riding&&health==20
            &&!("minecraft:drowned".equals(type)&&"minecraft:trident".equals(hand))
            &&Double.isFinite(boatDistance)&&boatDistance>=0&&boatDistance<=18
            &&Double.isFinite(playerDistance)&&playerDistance>=0&&playerDistance<=64
            &&Double.isFinite(heightDifference)&&Math.abs(heightDifference)<=4;
    }
}

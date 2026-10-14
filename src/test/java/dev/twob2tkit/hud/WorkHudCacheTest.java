package dev.twob2tkit.hud;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class WorkHudCacheTest {
    private JsonObject json(String s){return JsonParser.parseString(s).getAsJsonObject();}
    private JsonObject state(){return json("{connected:true,world_session:'w',control_revision:3,supervision_lease:{id:'lease',kind:'materials',world_session:'w',job_session:'task'}}");}
    private JsonObject job(){return json("{active:true,world_session:'w',task_session:'task',control_revision:3,updated_at:10000,title:'地图',done:773,total:16512,phase:'铺设木板'}");}
    @Test void ownedNavigationRevisionAndMailboxGapPreserveVerifiedProgressBriefly() {
        var cache=new WorkHudCache();var s=state();
        assertEquals("773/16512",cache.select(s,job(),10001).progress());
        s.addProperty("control_revision",4);
        assertEquals("773/16512",cache.select(s,job(),10250).progress());
        assertEquals("铺设木板",cache.select(s,null,15001).phase());
        assertNull(cache.select(s,null,15002));
    }
    @Test void manualWorldOwnerParkingOrRevisionRollbackClearsTheOldTask() {
        for(String change:new String[]{"manual","world","owner","lease","parking","rollback"}) {
            var cache=new WorkHudCache();var s=state();cache.select(s,job(),10001);
            switch(change) {
                case "manual"->s.addProperty("manual_movement",true);
                case "world"->s.addProperty("world_session","other");
                case "owner"->s.getAsJsonObject("supervision_lease").addProperty("job_session","other");
                case "lease"->s.getAsJsonObject("supervision_lease").addProperty("id","other");
                case "parking"->s.getAsJsonObject("supervision_lease").addProperty("kind","parking");
                case "rollback"->s.addProperty("control_revision",2);
            }
            assertNull(cache.select(s,null,10002),change);
        }
    }
    @Test void currentProtectionIsAppliedWithoutChangingTheRetainedQuota() {
        var cache=new WorkHudCache();var s=state();cache.select(s,job(),10001);
        s.addProperty("control_revision",4);s.addProperty("guard_busy",true);
        var result=cache.select(s,null,10002);
        assertEquals("773/16512",result.progress());assertEquals("防护中",result.phase());
        s.addProperty("guard_busy",false);assertEquals("铺设木板",cache.select(s,null,10003).phase());
    }
    @Test void explicitlyClosedTaskIsNotKeptByTheDisplayCache() {
        var cache=new WorkHudCache();var s=state();var j=job();cache.select(s,j,10001);
        j.addProperty("active",false);assertNull(cache.select(s,j,10002));
    }
}

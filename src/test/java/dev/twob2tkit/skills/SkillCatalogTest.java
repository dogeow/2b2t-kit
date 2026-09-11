package dev.twob2tkit.skills;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import com.google.gson.*;
import java.nio.file.*;
import static org.junit.jupiter.api.Assertions.*;

class SkillCatalogTest {
    @TempDir Path temp;
    @Test void hmclJavaHomeOverrideCannotRedirectTheSharedCatalog(){
        assertEquals(Path.of("/Users/sam/.minecraft-kit/skills/catalog.json"),SkillCatalog.resolvePath("","/Users/sam",null,"/Applications"));
    }
    @Test void explicitCatalogPathAndMissingEnvironmentAreHandled(){
        assertEquals(Path.of("/chosen/catalog.json"),SkillCatalog.resolvePath("/chosen/catalog.json","/Users/sam",null,"/Applications"));
        assertEquals(Path.of("/profile/.minecraft-kit/skills/catalog.json"),SkillCatalog.resolvePath("",null,"/profile","/Applications"));
        assertEquals(Path.of("/fallback/.minecraft-kit/skills/catalog.json"),SkillCatalog.resolvePath("","relative",null,"/fallback"));
    }
    private String catalog(int count,String status,long updated){
        var root=new JsonObject();root.addProperty("schema",1);root.addProperty("updated_ms",updated);var array=new JsonArray();
        for(int i=0;i<count;i++){
            var s=new JsonObject();s.addProperty("name","skill_"+i);s.addProperty("title","采集技能 "+i);s.addProperty("description","采集原木并核对背包");s.addProperty("version",1);s.addProperty("status",status);s.addProperty("origin","candidate");
            s.addProperty("successful_runs",status.equals("verified")?2:0);s.add("parameters",new JsonObject());s.add("steps",new JsonArray());s.add("success",new JsonArray());array.add(s);
        }root.add("skills",array);return root.toString();
    }
    @Test void theListIncludesEverySkillAndSearchIncludesDescription(){
        var view=SkillCatalog.parse(catalog(500,"candidate",1000));assertEquals(500,view.entries().size());
        assertTrue(view.entries().getFirst().search().contains("原木"));assertTrue(view.entries().getFirst().search().contains("skill_"));
    }
    @Test void candidateAndVerifiedAreDistinctAndEmptyIsNotMissing(){
        var candidate=SkillCatalog.parse(catalog(1,"candidate",1000)).entries().getFirst();assertFalse(candidate.verified());assertTrue(candidate.statusLabel().contains("待验证"));
        assertTrue(SkillCatalog.parse(catalog(1,"verified",1000)).entries().getFirst().verified());
        assertEquals("",SkillCatalog.parse(catalog(0,"candidate",1000)).error());assertFalse(SkillCatalog.read(temp.resolve("missing")).error().isEmpty());
    }
    @Test void malformedFileFailsAsAReadableStatus()throws Exception{
        var p=temp.resolve("catalog.json");Files.writeString(p,"{unfinished");assertTrue(SkillCatalog.read(p).error().contains("读取失败"));
    }
    @Test void stalePublisherIsVisibleWhileSavedSkillsRemainAvailable(){
        var view=SkillCatalog.parse(catalog(3,"candidate",1000));assertTrue(view.summary(2000).contains("在线"));assertTrue(view.summary(20000).contains("未更新"));assertEquals(3,view.entries().size());
    }
    private void await(SkillCatalogFeed feed,int count)throws Exception{
        long end=System.currentTimeMillis()+2500;
        while(System.currentTimeMillis()<end){feed.revision();if(feed.view().entries().size()==count)return;Thread.sleep(5);}
        fail("catalog update did not arrive");
    }
    @Test void backgroundFeedPicksUpNewSkillsAndDoesNotRebuildForHeartbeatOnly()throws Exception{
        var p=temp.resolve("catalog.json");Files.writeString(p,catalog(1,"candidate",1000));var feed=new SkillCatalogFeed(p);await(feed,1);long first=feed.revision();
        Files.writeString(p,catalog(1,"candidate",2000));feed.refresh();long end=System.currentTimeMillis()+2500;
        while(feed.view().updatedMs()!=2000&&System.currentTimeMillis()<end){feed.revision();Thread.sleep(5);}
        assertEquals(2000,feed.view().updatedMs());assertEquals(first,feed.revision());
        Files.writeString(p,catalog(8,"candidate",3000));feed.refresh();await(feed,8);assertTrue(feed.revision()>first);
    }
}

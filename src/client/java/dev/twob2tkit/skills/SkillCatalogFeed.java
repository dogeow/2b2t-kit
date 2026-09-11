package dev.twob2tkit.skills;

import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/** File reading happens off the render thread. Heartbeats alone do not rebuild the list. */
public final class SkillCatalogFeed {
    private final Path path;
    private SkillCatalog.View view=new SkillCatalog.View(List.of(),0,"正在读取技能目录…");
    private CompletableFuture<SkillCatalog.View> pending;
    private long nextPoll,revision;
    public SkillCatalogFeed(Path path){this.path=path;}
    public SkillCatalog.View view(){return view;}
    public long revision(){
        if(pending!=null&&pending.isDone()){
            var next=pending.join();pending=null;
            if(!next.entries().equals(view.entries())||!next.error().equals(view.error()))revision++;
            view=next;
        }
        long now=System.currentTimeMillis();
        if(pending==null&&now>=nextPoll){nextPoll=now+1000;pending=CompletableFuture.supplyAsync(()->SkillCatalog.read(path));}
        return revision;
    }
    public void refresh(){nextPoll=0;revision();}
}

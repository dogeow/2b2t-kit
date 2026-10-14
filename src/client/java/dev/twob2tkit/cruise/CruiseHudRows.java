package dev.twob2tkit.cruise;

import dev.twob2tkit.hud.WorkHudModel;
import java.util.ArrayList;
import java.util.List;

/** Independent task and navigation rows; arrival notices never replace task progress. */
public final class CruiseHudRows {
    private CruiseHudRows() {}
    public record Row(String line,boolean attention,boolean notice) {}
    public static List<Row> select(WorkHudModel.Summary task,String cruise,boolean notice) {
        var rows=new ArrayList<Row>(2);
        if(task!=null)rows.add(new Row("任务 · "+task.line(),task.attention(),false));
        String line=WorkHudModel.clean(cruise==null?"":cruise);
        if(!line.isBlank())rows.add(new Row(line.startsWith("巡航")?line:"巡航 · "+line,false,notice));
        return List.copyOf(rows);
    }
}

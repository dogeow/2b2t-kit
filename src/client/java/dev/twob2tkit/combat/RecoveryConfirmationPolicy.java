package dev.twob2tkit.combat;

import com.google.gson.*;

/** One incident, direct human chat only. A scheduled goal continuation is not authorization. */
public final class RecoveryConfirmationPolicy {
    private RecoveryConfirmationPolicy() {}
    public static Long number(JsonElement value) {
        if(value==null||!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber())return null;
        String text=value.getAsString();if(!text.matches("0|[1-9][0-9]*"))return null;
        try{return Long.parseLong(text);}catch(NumberFormatException invalid){return null;}
    }
    public static boolean flag(JsonElement value,boolean expected) {
        return value!=null&&value.isJsonPrimitive()&&value.getAsJsonPrimitive().isBoolean()
            &&value.getAsBoolean()==expected;
    }
    private static String text(JsonObject value,String key) {
        var item=value.get(key);
        return item!=null&&item.isJsonPrimitive()&&item.getAsJsonPrimitive().isString()?item.getAsString():"";
    }
    public static void requireOrigin(JsonObject record,String server,String dimension,String player) {
        String origin=text(record,"server"),dim=text(record,"dimension"),person=text(record,"player");
        java.util.function.UnaryOperator<String> normalize=s->s.toLowerCase(java.util.Locale.ROOT).replaceFirst(":25565$","");
        if(origin.isBlank()||!normalize.apply(origin).equals(normalize.apply(server))
                ||!dim.isBlank()&&!dim.equals(dimension)||!person.isBlank()&&!person.equals(player))
            throw new IllegalStateException("Recovery confirmation must use the incident's server, dimension and player");
    }
    public static void require(JsonObject request,long now,long hold,String world,long revision,
            boolean alive,double health,int food,boolean idle,boolean safeScreen,boolean quiet) {
        Long target=number(request.get("confirmed_hold_time")),confirmed=number(request.get("confirmation_recorded_at"));
        Long expected=number(request.get("expected_revision")),expires=number(request.get("expires_at"));
        String reference=text(request,"authorization_reference"),quote=text(request,"authorization_text");
        if(hold<=0||target==null||target!=hold||confirmed==null||confirmed<hold||confirmed>now
                ||!flag(request.get("confirmed_by_user"),true)||!text(request,"authorization_channel").equals("human_chat")
                ||reference.isBlank()||reference.length()>256||quote.isBlank()||quote.length()>512)
            throw new IllegalStateException("A direct human chat confirmation for this exact health incident is required");
        if(world==null||world.isBlank()||!world.equals(text(request,"world_session"))||expected==null||expected!=revision
                ||expires==null||expires<now||expires-now>15000)
            throw new IllegalStateException("Recovery confirmation belongs to an old world or control scope");
        if(!alive||!Double.isFinite(health)||health<18||food<8||!idle||!safeScreen||!quiet)
            throw new IllegalStateException("Recover safely first: healthy alive player, quiet scene and idle control required");
    }
    public static boolean explicitAck(JsonObject record,long hold) {
        if(record==null||!flag(record.get("active"),false)||!flag(record.get("confirmed_by_user"),true)
                ||!text(record,"cleared_by").equals("explicit_chat")
                ||!text(record,"authorization_channel").equals("human_chat")
                ||text(record,"authorization_reference").isBlank()||text(record,"authorization_reference").length()>256
                ||text(record,"authorization_text").isBlank()||text(record,"authorization_text").length()>512)return false;
        Long target=number(record.get("confirmed_hold_time")),confirmed=number(record.get("confirmation_recorded_at"));
        Long cleared=number(record.get("cleared_at"));
        return target!=null&&confirmed!=null&&cleared!=null&&target>=hold&&confirmed>=target&&cleared>=confirmed&&cleared>hold;
    }
    public static void copyGrant(JsonObject destination,JsonObject request,long now) {
        for(String key:new String[]{"confirmed_by_user","authorization_channel","authorization_reference","authorization_text",
                "confirmed_hold_time","confirmation_recorded_at"})destination.add(key,request.get(key).deepCopy());
        destination.addProperty("active",false);destination.addProperty("cleared_by","explicit_chat");
        destination.addProperty("cleared_at",now);
    }
}

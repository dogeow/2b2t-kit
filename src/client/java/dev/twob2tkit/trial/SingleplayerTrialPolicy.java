package dev.twob2tkit.trial;

/** Pure scope checks for explicitly registered, unpublished local trial saves. */
public final class SingleplayerTrialPolicy {
    private SingleplayerTrialPolicy() {}
    public static boolean world(boolean integrated,boolean remote,boolean published,boolean survival,boolean hardcore,String actual,String registered){
        return integrated&&!remote&&!published&&survival&&!hardcore&&actual!=null&&!actual.isBlank()&&actual.equals(registered);
    }
    public static boolean owner(String trial,String run,String expectedTrial,String expectedRun){
        return trial!=null&&run!=null&&!trial.isBlank()&&!run.isBlank()&&trial.equals(expectedTrial)&&run.equals(expectedRun);
    }
    public static boolean respawn(boolean scoped,boolean dead,boolean deathScreen,int epoch,int requested,int lastRequested,long deadMillis){
        return scoped&&dead&&deathScreen&&epoch>0&&epoch==requested&&epoch!=lastRequested&&deadMillis>=1000;
    }
}

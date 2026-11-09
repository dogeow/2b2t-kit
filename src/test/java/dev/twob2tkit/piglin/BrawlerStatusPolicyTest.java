package dev.twob2tkit.piglin;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BrawlerStatusPolicyTest {
    @Test void reportsKnownTargetsOutsideReach() {
        assertTrue(BrawlerStatusPolicy.piglinStatus(40,3,true).contains("40.0格"));
        assertTrue(BrawlerStatusPolicy.piglinStatus(40,3,true).contains("3.0格"));
        assertTrue(BrawlerStatusPolicy.piglinStatus(64,3,true).contains("附近有猪人"));
    }
    @Test void distinguishesDelegatedMeleeAndUnknownTargets() {
        assertTrue(BrawlerStatusPolicy.piglinStatus(3,3,false).contains("Meteor"));
        assertTrue(BrawlerStatusPolicy.piglinStatus(Double.POSITIVE_INFINITY,3,true).contains("未发现"));
        assertTrue(BrawlerStatusPolicy.piglinStatus(65,3,true).contains("未发现"));
        assertTrue(BrawlerStatusPolicy.piglinStatus(3,3,true).contains("等待攻击条件"));
    }
}

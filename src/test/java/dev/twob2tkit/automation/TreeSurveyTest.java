package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class TreeSurveyTest {
 @Test void identifiesOnlyNaturalLogSpecies(){assertTrue(TreeSurvey.supported("minecraft:spruce_log"));assertTrue(TreeSurvey.supported("minecraft:birch_log"));assertFalse(TreeSurvey.supported("minecraft:stripped_spruce_log"));assertFalse(TreeSurvey.supported("minecraft:spruce_planks"));assertFalse(TreeSurvey.supported(null));}
}

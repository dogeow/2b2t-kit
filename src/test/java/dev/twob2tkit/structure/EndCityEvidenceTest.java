package dev.twob2tkit.structure;

import java.util.List;
import dev.twob2tkit.structure.EndCitySurvey.Observation;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeAll;

import static dev.twob2tkit.structure.StructureLocator.EndCityChunk.*;
import static dev.twob2tkit.structure.StructureLocator.EndCityObservation.*;
import static org.junit.jupiter.api.Assertions.*;

class EndCityEvidenceTest {
    @BeforeAll
    static void bootstrapMinecraft() {
        net.minecraft.SharedConstants.tryDetectVersion();
        net.minecraft.server.Bootstrap.bootStrap();
    }

    @Test
    void distinguishesAnEmptySiteFromMissingDataAndBuildingEvidence() {
        assertEquals(ABSENT, StructureLocator.observeEndCity(7,-9,(x,z) -> EMPTY));
        assertEquals(PENDING, StructureLocator.observeEndCity(7,-9,(x,z) -> x == 8 && z == -10 ? UNKNOWN : EMPTY));
        assertEquals(TRACES, StructureLocator.observeEndCity(7,-9,(x,z) -> x == 8 && z == -10 ? BUILDING : EMPTY));
        assertEquals(PRESENT, StructureLocator.observeEndCity(7,-9,(x,z) -> x == 8 && z == -10 ? CITY : UNKNOWN));
    }

    @Test
    void advancesAfterVerifiedMissAndStopsAtTheFirstCity() {
        var first = new StructureLocator.Hit(StructureLocator.Kind.END_CITY,1,2,3,"末地城");
        var second = new StructureLocator.Hit(StructureLocator.Kind.END_CITY,400,2,401,"末地城");
        var survey = new EndCitySurvey(List.of(first,second));
        assertEquals(EndCitySurvey.Decision.WAIT, survey.observe(Observation.NO_CITY));
        assertEquals(EndCitySurvey.Decision.WAIT, survey.observe(Observation.PENDING));
        assertEquals(EndCitySurvey.Decision.WAIT, survey.observe(Observation.NO_CITY));
        assertEquals(EndCitySurvey.Decision.NEXT, survey.observe(Observation.NO_CITY));
        assertEquals(second, survey.target());
        assertEquals(EndCitySurvey.Decision.FOUND, survey.observe(Observation.LIVE_SHULKER));
        assertEquals(second, survey.target());
    }

    @Test
    void waitsForEntityPacketsAndSkipsACityWithNoLiveShulkers() {
        var first = new StructureLocator.Hit(StructureLocator.Kind.END_CITY,1,2,3,"末地城");
        var second = new StructureLocator.Hit(StructureLocator.Kind.END_CITY,400,2,401,"末地城");
        var survey = new EndCitySurvey(List.of(first,second));
        for (int sample = 0; sample < 7; sample++)
            assertEquals(EndCitySurvey.Decision.WAIT,survey.observe(Observation.NO_SHULKERS));
        assertEquals(EndCitySurvey.Decision.NEXT,survey.observe(Observation.NO_SHULKERS));
        assertEquals(second,survey.target());
        assertEquals(EndCitySurvey.Decision.FOUND,survey.observe(Observation.LIVE_SHULKER));
    }

    @Test
    void coastingAtArrivalDoesNotDiscardTheCandidate() {
        var site = new StructureLocator.Hit(StructureLocator.Kind.END_CITY,4519,-54937,20,"末地城");
        var survey = new EndCitySurvey(List.of(site));
        survey.beginArrival();
        assertEquals(EndCitySurvey.Position.SETTLING,survey.observePosition(14,1.5));
        for (int i = 0; i < 3; i++)
            assertEquals(EndCitySurvey.Position.SETTLING,survey.observePosition(18,.1));
        assertEquals(EndCitySurvey.Position.IN_RANGE,survey.observePosition(18,.1));
        assertEquals(site,survey.target());
        assertEquals(EndCitySurvey.Position.RECENTER,survey.observePosition(26,.1));
        assertEquals(site,survey.target());
    }

    @Test
    void waitsPastTheOldDeadlineThenContinuesAfterTheServerSuppliesEmptyChunks() {
        var first = new StructureLocator.Hit(StructureLocator.Kind.END_CITY,4903,-57225,3,"末地城");
        var next = new StructureLocator.Hit(StructureLocator.Kind.END_CITY,5200,-57225,300,"末地城");
        var survey = new EndCitySurvey(List.of(first,next));
        for (int i=0;i<240;i++) assertEquals(EndCitySurvey.Decision.WAIT,survey.observe(Observation.PENDING));
        assertEquals(first,survey.target());
        assertEquals(EndCitySurvey.Decision.WAIT,survey.observe(Observation.NO_CITY));
        assertEquals(EndCitySurvey.Decision.NEXT,survey.observe(Observation.NO_CITY));
        assertEquals(next,survey.target());
    }
}

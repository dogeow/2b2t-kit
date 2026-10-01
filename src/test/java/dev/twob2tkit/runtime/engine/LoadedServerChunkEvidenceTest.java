package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LoadedServerChunkEvidenceTest {
    static final class DerivedFakeChunk extends de.johni0702.minecraft.bobby.FakeChunk {}
    static final class OrdinaryChunkClass {}

    @Test void rejectsBobbyFakeChunkAndAnySubclassBeforeTrustingTheOptionalApi() {
        assertTrue(LoadedServerChunkEvidence.isBobbyOwnedChunk(
            de.johni0702.minecraft.bobby.FakeChunk.class));
        assertTrue(LoadedServerChunkEvidence.isBobbyOwnedChunk(DerivedFakeChunk.class));
        assertFalse(LoadedServerChunkEvidence.isServerChunkClass(
            DerivedFakeChunk.class, false, null));
    }

    @Test void vanillaClientChunkClassRemainsEligibleWithoutBobby() {
        assertTrue(LoadedServerChunkEvidence.isServerChunkClass(
            OrdinaryChunkClass.class, false, null));
    }

    @Test void installedButUnresolvedBobbyFailsClosed() {
        assertFalse(LoadedServerChunkEvidence.isServerChunkClass(
            OrdinaryChunkClass.class, true, null));
    }

    @Test void resolvedBobbyAcceptsOnlyClassesOutsideItsFakeHierarchy() {
        Class<?> fake = de.johni0702.minecraft.bobby.FakeChunk.class;
        assertTrue(LoadedServerChunkEvidence.isServerChunkClass(
            OrdinaryChunkClass.class, true, fake));
        assertFalse(LoadedServerChunkEvidence.isServerChunkClass(fake, true, fake));
        assertFalse(LoadedServerChunkEvidence.isServerChunkClass(
            DerivedFakeChunk.class, true, fake));
    }
}

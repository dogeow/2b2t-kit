package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MushroomStemPlacementPolicyTest {
    @BeforeAll static void bootstrap() {
        net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();
    }
    @Test void only_all_six_true_stem_faces_without_same_type_neighbors_are_allowed() {
        var state=Blocks.MUSHROOM_STEM.defaultBlockState();var pos=BlockPos.ZERO;
        assertTrue(MushroomStemPlacementPolicy.allFaces(state));
        assertTrue(MushroomStemPlacementPolicy.isolated(state,pos,p->Blocks.AIR.defaultBlockState()));
        assertFalse(MushroomStemPlacementPolicy.allFaces(Blocks.STONE.defaultBlockState()));
        assertFalse(MushroomStemPlacementPolicy.allFaces(Blocks.BROWN_MUSHROOM_BLOCK.defaultBlockState()));
        assertFalse(MushroomStemPlacementPolicy.allFaces(state.setValue(BlockStateProperties.NORTH,false)));
        for(Direction direction:Direction.values())
            assertFalse(MushroomStemPlacementPolicy.isolated(state,pos,p->p.equals(pos.relative(direction))?state:Blocks.STONE.defaultBlockState()));
    }
}

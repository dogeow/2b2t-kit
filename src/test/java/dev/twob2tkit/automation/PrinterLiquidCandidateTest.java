package dev.twob2tkit.automation;

import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PrinterLiquidCandidateTest {
    public static class Candidate {
        public BlockPos blockPos=BlockPos.ZERO;
        public BlockState targetState=Blocks.WATER.defaultBlockState();
    }
    @BeforeAll static void bootstrap(){SharedConstants.tryDetectVersion();Bootstrap.bootStrap();}
    @Test void ownedNativePrinterRejectsTheRealLiquidCandidateBeforeConsultingWorldOrQueuingInput()throws Exception{
        var field=ProfessionalPrinter.class.getDeclaredField("owned");field.setAccessible(true);
        boolean old=field.getBoolean(null);
        try{
            field.setBoolean(null,true);
            assertFalse(ProfessionalPrinter.observeCandidate(new Candidate()));
            var lava=new Candidate();lava.targetState=Blocks.LAVA.defaultBlockState();
            assertFalse(ProfessionalPrinter.observeCandidate(lava));
        }finally{field.setBoolean(null,old);}
    }
}

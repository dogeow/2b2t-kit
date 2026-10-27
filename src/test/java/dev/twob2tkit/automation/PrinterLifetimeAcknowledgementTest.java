package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class PrinterLifetimeAcknowledgementTest {
    ClassNode code()throws Exception{
        var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/ProfessionalPrinter.class")){
            assertNotNull(in);new ClassReader(in).accept(c,0);
        }return c;
    }
    @Test void stationStartsNeverResetTheCumulativeServerCount()throws Exception{
        var writers=new ArrayList<String>();
        for(var m:code().methods)for(var i:m.instructions)
            if(i instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTSTATIC&&f.name.equals("serverConfirmedTotal"))writers.add(m.name);
        assertEquals(List.of("serverBlock"),writers);
    }
    @Test void cumulativeCountAdvancesAtTheExistingAcknowledgementBoundary()throws Exception{
        var m=code().methods.stream().filter(v->v.name.equals("serverBlock")).findFirst().orElseThrow();
        int ack=-1,station=-1,total=-1,index=0;
        for(var i:m.instructions){
            if(i instanceof MethodInsnNode call&&call.owner.endsWith("ConfirmedPlacementPacer")&&call.name.equals("acknowledge"))ack=index;
            if(i instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTSTATIC){
                if(f.name.equals("confirmedPlacements"))station=index;
                if(f.name.equals("serverConfirmedTotal"))total=index;
            }index++;
        }
        assertTrue(ack>=0&&station>ack&&total>station);
    }
}

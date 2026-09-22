package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class SchematicLoadPolicyTest {
    @Test void allocatedOrMissingSchematicChunksMustNotBeMistakenForAir(){
        for(String state:new String[]{"NEW","EMPTY","UNLOADED","PROTO","LOADED","NO_WORLD_EXCEPTION"})assertFalse(SchematicLoadPolicy.ready(state),state);
        assertTrue(SchematicLoadPolicy.ready("FILLED"));assertTrue(SchematicLoadPolicy.ready("RENDERED"));
    }
    @Test void liveScanChecksSchematicReadinessBeforeReadingAnyBlock()throws Exception{
        var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/builder/ProjectionBuildJob.class")){new ClassReader(in).accept(c,0);}
        var load=c.methods.stream().filter(m->m.name.equals("load")).findFirst().orElseThrow();int gate=-1,read=-1,i=0;
        for(var ins:load.instructions){if(ins instanceof MethodInsnNode m){if(m.name.equals("loadingReason"))gate=i;if(read<0&&m.name.equals("getBlockState"))read=i;}i++;}
        assertTrue(gate>=0&&read>gate);
    }
}

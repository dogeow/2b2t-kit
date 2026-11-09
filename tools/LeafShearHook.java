import org.objectweb.asm.*;
import java.nio.file.*;
/** Insert the source's one leaf tick call into an immutable deployed engine.
 * This avoids deploying unrelated working-tree engine modifications.
 */
public final class LeafShearHook {
    public static void main(String[] args)throws Exception{
        byte[] original=Files.readAllBytes(Path.of(args[0]));int[] methods={0},hooks={0};
        new ClassReader(original).accept(new ClassVisitor(Opcodes.ASM9){
            public MethodVisitor visitMethod(int a,String n,String d,String s,String[] e){
                if(n.equals("tickStandaloneGuard")&&d.equals("(Lnet/minecraft/client/Minecraft;Z)Z"))methods[0]++;
                return new MethodVisitor(Opcodes.ASM9){public void visitMethodInsn(int op,String owner,String name,String desc,boolean itf){if(owner.endsWith("/LeafShearBatch"))hooks[0]++;}};
            }
        },0);
        if(methods[0]!=1||hooks[0]!=0)throw new IllegalStateException("Expected exactly one unpatched guard tick");
        ClassReader reader=new ClassReader(original);ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);
        reader.accept(new ClassVisitor(Opcodes.ASM9,writer){
            public MethodVisitor visitMethod(int a,String n,String d,String s,String[] e){
                MethodVisitor next=super.visitMethod(a,n,d,s,e);
                if(!n.equals("tickStandaloneGuard")||!d.equals("(Lnet/minecraft/client/Minecraft;Z)Z"))return next;
                return new MethodVisitor(Opcodes.ASM9,next){public void visitCode(){
                    super.visitCode();visitVarInsn(Opcodes.ALOAD,1);visitVarInsn(Opcodes.ILOAD,2);visitVarInsn(Opcodes.ALOAD,0);
                    visitFieldInsn(Opcodes.GETFIELD,"dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine","active","Z");
                    visitMethodInsn(Opcodes.INVOKESTATIC,"dev/twob2tkit/runtime/engine/LeafShearBatch","tick","(Lnet/minecraft/client/Minecraft;ZZ)V",false);
                }};
            }
        },0);
        Files.write(Path.of(args[1]),writer.toByteArray());
    }
}

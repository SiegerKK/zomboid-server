package sieger.server;

import java.lang.instrument.*;
import java.security.*;
import java.util.HexFormat;
import net.bytebuddy.jar.asm.*;

/** Dedicated-server observer. No Lua files, MODS entry or checksum changes. */
public final class Agent {
    static final String EVENT_SHA="9706f17e9b5e095a0e24230dc944de5d552fa62c997214636c4deb4957cf354b";
    private static volatile boolean enabled;
    public static void premain(String world, Instrumentation inst) {
        if (world==null || !world.matches("[A-Za-z0-9][A-Za-z0-9_-]{0,39}"))
            throw new IllegalArgumentException("Explicit world required");
        Animals.world=world;
        inst.addTransformer(new Transformer());
    }
    private static final class Transformer implements ClassFileTransformer {
        public byte[] transform(ClassLoader loader,String name,Class<?> c,
                ProtectionDomain domain,byte[] bytes) {
            if (!"zombie/Lua/LuaEventManager".equals(name)) return null;
            try {byte[] result=instrument(bytes);enabled=true;return result;}
            catch(Throwable e){System.err.println("SIEGER_SERVER disabled: event ABI/hash mismatch");return null;}
        }
    }
    private static final class EventVisitor extends ClassVisitor {
        final int[] hooks;
        EventVisitor(ClassVisitor out,int[] hooks){super(Opcodes.ASM9,out);this.hooks=hooks;}
        public MethodVisitor visitMethod(int access,String name,String desc,String sig,String[] exceptions){
            MethodVisitor base=super.visitMethod(access,name,desc,sig,exceptions);
            if (!name.equals("triggerEvent") || !desc.startsWith("(Ljava/lang/String;") ||
                    (access&Opcodes.ACC_STATIC)==0)return base;
            hooks[0]++;return new TickVisitor(base);
        }
    }
    private static final class TickVisitor extends MethodVisitor {
        TickVisitor(MethodVisitor out){super(Opcodes.ASM9,out);}
        public void visitCode(){super.visitCode();visitVarInsn(Opcodes.ALOAD,0);
            visitMethodInsn(Opcodes.INVOKESTATIC,"sieger/server/Agent","onEvent","(Ljava/lang/String;)V",false);}
    }
    public static byte[] instrument(byte[] bytes)throws Exception{
        if (!EVENT_SHA.equals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))))
            throw new IllegalArgumentException("Unsupported event class");
        ClassReader reader=new ClassReader(bytes);
        ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);
        int[] hooks={0};reader.accept(new EventVisitor(writer,hooks),0);
        if(hooks[0]==0)throw new IllegalArgumentException("No event hook");
        return writer.toByteArray();
    }
    public static void onEvent(String name){
        if(!enabled || !"OnTickEvenPaused".equals(name))return;
        try{Animals.tick();}catch(Throwable e){Animals.fail(e);}
    }
}

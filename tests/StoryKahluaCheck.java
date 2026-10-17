import java.nio.file.*;
import java.lang.reflect.*;
public class StoryKahluaCheck {
  public static void main(String[] args) throws Exception {
    Class<?> platformType=Class.forName("se.krka.kahlua.vm.Platform");
    Class<?> tableType=Class.forName("se.krka.kahlua.vm.KahluaTable");
    Class<?> platformClass=Class.forName("se.krka.kahlua.j2se.J2SEPlatform");
    Object platform=platformClass.getConstructor().newInstance();
    Object env=platformClass.getMethod("newEnvironment").invoke(platform);
    Object arg=platformClass.getMethod("newTable").invoke(platform);
    Method rawset=tableType.getMethod("rawset",Object.class,Object.class);
    rawset.invoke(env,"arg",arg);
    // Engine inventory names arrive as Java strings, not Lua source literals.
    rawset.invoke(env,"_unicodeBandage","Бинт");
    rawset.invoke(env,"_unicodeNote","Дневник \"Медик\"");
    rawset.invoke(env,"_liveHex0","d094d0bed0bad182d0bed1802022d09cd0b8d0bbd0bbd0b5d18022");
    rawset.invoke(env,"_liveHex1","d0a1d182d180d0b0d0bdd0b8d186d0b020d0bfd0b5d180d0b2d0b0d18f");
    rawset.invoke(env,"_liveHex2","d0a1d182d180d0b0d0bdd0b8d186d0b020d0b2d182d0bed180d0b0d18f");
    rawset.invoke(env,"_liveHex3","d09fd0b8d181d18cd0bcd0be");
    rawset.invoke(env,"_liveHex4","d09fd183d181d182d18c20d0b4d0bed0b6d0b4d18c20d0b7d0b0d0bad0bed0bdd187d0b8d182d181d18f");
    rawset.invoke(env,"_liveTitle","Доктор \"Миллер\"");
    rawset.invoke(env,"_livePage","Страница вторая");
    rawset.invoke(env,"_scanSource",Files.readString(Path.of(args[1])));
    String src=Files.readString(Path.of(args[0])).replace("dofile(runtime)","assert(loadstring(_scanSource, 'SiegerStoryAreaScan.lua'))()");
    Object closure=Class.forName("se.krka.kahlua.luaj.compiler.LuaCompiler")
      .getMethod("loadstring",String.class,String.class,tableType).invoke(null,src,"story_area_scan.lua",env);
    Class<?> threadClass=Class.forName("se.krka.kahlua.vm.KahluaThread");
    Object thread=threadClass.getConstructor(platformType,tableType).newInstance(platform,env);
    threadClass.getField("debugOwnerThread").set(thread,Thread.currentThread());
    Object[] result=(Object[])threadClass.getMethod("pcall",Object.class,Object[].class).invoke(thread,closure,new Object[0]);
    if(args.length>2) Files.writeString(Path.of(args[2]),(String)tableType.getMethod("rawget",Object.class).invoke(env,"_firstScanData"));
    if (!Boolean.TRUE.equals(result[0])) throw new RuntimeException(java.util.Arrays.toString(result));
    System.out.println("PASS: exact pinned Kahlua VM executes Story harness");
  }
}

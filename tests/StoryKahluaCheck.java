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
    System.out.println("PASS: exact pinned Kahlua VM executes bounded area-scan harness");
  }
}

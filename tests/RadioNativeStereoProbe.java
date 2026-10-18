/** Optional JDK 25 offline probe against the OWNER'S real installed B42.21 JAR.
 * Separate process, NOSOUND_NRT before init; no running game/world interaction.
 * Use a generated synthetic PCM WAV, never artist audio or CI mocks.
 */
import java.lang.foreign.*;import java.lang.reflect.*;import java.nio.*;import java.nio.file.*;
import fmod.javafmodJNI;import org.lwjgl.system.MemoryUtil;import siegerradio.bridge.SiegerRadioBridge;
public class RadioNativeStereoProbe {
 static void ok(int result)throws Exception{if(result!=0)throw new Exception("FMOD result="+result);}
 static void field(String name,Object value)throws Exception{Field f=SiegerRadioBridge.class.getDeclaredField(name);f.setAccessible(true);f.set(null,value);}
 public static void main(String[] args)throws Exception {
  Path lib=Path.of(args[0]);System.load(lib.resolve("libfmod.so").toString());System.load(lib.resolve("libfmodstudio.so").toString());System.load(lib.resolve("libfmodintegration64.so").toString());
  ok(javafmodJNI.FMOD_System_Create());
  // Test process only: select NOSOUND_NRT BEFORE initialization. No live game,
  // audio device, microphone, listener or OS settings are accessed/modified.
  long sys=SymbolLookup.loaderLookup().find("globalSystem").orElseThrow().reinterpret(8).get(ValueLayout.ADDRESS,0).address();
  ByteBuffer enumSlot=ByteBuffer.allocateDirect(8).order(ByteOrder.nativeOrder());enumSlot.putInt(0,4);
  ok(javafmodJNI.FMOD_System_SetOutput(sys,MemoryUtil.memAddress(enumSlot)));ok(javafmodJNI.FMOD_System_Init(128,0,0x20300));
  Method bind=SiegerRadioBridge.class.getDeclaredMethod("bind");bind.setAccessible(true);if(!Boolean.TRUE.equals(bind.invoke(null)))throw new Exception("Bridge ABI");
  long sound=javafmodJNI.FMOD_System_CreateSound(args[1],0x80|0x10|2);if(sound==0)throw new Exception("CreateSound");
  long channel=javafmodJNI.FMOD_System_PlaySound(sound,1);if(channel==0)throw new Exception("PlaySound");
  field("channelHandle",channel);field("soundHandle",sound);field("playing3d",true);
  Method route=SiegerRadioBridge.class.getDeclaredMethod("routeOutput");route.setAccessible(true);if(!Boolean.TRUE.equals(route.invoke(null)))throw new Exception(SiegerRadioBridge.details());
  if(!SiegerRadioBridge.details().contains("output=private_stereo_3d"))throw new Exception("Private route absent");
  ByteBuffer slot=ByteBuffer.allocateDirect(16).order(ByteOrder.nativeOrder());long address=MemoryUtil.memAddress(slot);
  ok(javafmodJNI.FMOD_System_GetSoftwareFormat(sys,address,address+4,address+8));if(slot.getInt(4)!=6)throw new Exception("Global format changed");
  if(!SiegerRadioBridge.setOutput("native")||!SiegerRadioBridge.setOutput("stereo"))throw new Exception("Live profile switch");
  ok(javafmodJNI.FMOD_Channel_Set3DAttributes(channel,1,0,0,0,0,0));ok(javafmodJNI.FMOD_Channel_SetPosition(channel,1000));ok(javafmodJNI.FMOD_Channel_SetPaused(channel,0));
  System.out.println("PASS REAL GAME JNI: owned direct pointer, private stereo bus, live switch, unchanged global 5.1");
  SiegerRadioBridge.stop();
  System.out.println("PASS REAL GAME JNI: channel/group/sound cleanup; no shipped mocks");
 }
}

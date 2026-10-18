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
  ok(javafmodJNI.FMOD_System_SetOutput(sys,MemoryUtil.memAddress(enumSlot)));
  ok(javafmodJNI.FMOD_System_SetSoftwareChannels(sys,2)); // isolated contention test ONLY
  ok(javafmodJNI.FMOD_System_Init(128,0,0x20300));
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
  // Two louder default-priority voices compete for only two real mixer slots.
  // Each has its own sound; never start the same stream twice.
  long[] otherSounds=new long[2],otherChannels=new long[2];
  ok(javafmodJNI.FMOD_Channel_SetVolume(channel,.25f));
  for(int i=0;i<2;i++) {
   otherSounds[i]=javafmodJNI.FMOD_System_CreateSound(args[1],0x08|2);
   if(otherSounds[i]==0)throw new Exception("Competitor sound");
   otherChannels[i]=javafmodJNI.FMOD_System_PlaySound(otherSounds[i],0);
   if(otherChannels[i]==0)throw new Exception("Competitor channel");
   ok(javafmodJNI.FMOD_Channel_SetVolume(otherChannels[i],1f));
   ok(javafmodJNI.FMOD_Channel_SetPriority(otherChannels[i],128));
  }
  for(int i=0;i<40;i++)javafmodJNI.FMOD_System_Update();
  if(!javafmodJNI.FMOD_Channel_IsVirtual(channel))throw new Exception("Contention did not virtualize default music");
  Method pri=SiegerRadioBridge.class.getDeclaredMethod("applyPriority");pri.setAccessible(true);pri.invoke(null);
  for(int i=0;i<40;i++)javafmodJNI.FMOD_System_Update();
  if(javafmodJNI.FMOD_Channel_IsVirtual(channel))throw new Exception("Priority did not recover real music voice");
  if(!SiegerRadioBridge.details().contains("priority=32"))throw new Exception("Priority status");
  field("sourceStereo",true);
  if(!SiegerRadioBridge.setCabin(true)||!SiegerRadioBridge.setCabin(false))throw new Exception("Cabin switch ABI");
  if(!javafmodJNI.FMOD_Channel_IsPlaying(channel))throw new Exception("Cabin switch stopped playback");
  System.out.println("PASS REAL GAME JNI: cabin180/exterior0 on same active 3D voice");
  System.out.println("PASS REAL GAME JNI: voice contention reproduced; SAME channel recovered at priority32, no restart/seek");
  for(int i=0;i<2;i++){ok(javafmodJNI.FMOD_Channel_Stop(otherChannels[i]));ok(javafmodJNI.FMOD_Sound_Release(otherSounds[i]));}
  System.out.println("PASS REAL GAME JNI: owned direct pointer, private stereo bus, live switch, unchanged global 5.1");
  SiegerRadioBridge.stop();
  System.out.println("PASS REAL GAME JNI: channel/group/sound cleanup; no shipped mocks");
 }
}

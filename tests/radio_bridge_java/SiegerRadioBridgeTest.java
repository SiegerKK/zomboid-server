import java.nio.file.*;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import siegerradio.bridge.SiegerRadioBridge;
import fmod.javafmod;
public final class SiegerRadioBridgeTest {
    private static void ok(boolean value,String reason) {if(!value)throw new AssertionError(reason);}
    private static byte[] pcm(int channels) {
        ByteBuffer b=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
        b.put("RIFF".getBytes(StandardCharsets.US_ASCII)).putInt(36);
        b.put("WAVEfmt ".getBytes(StandardCharsets.US_ASCII)).putInt(16);
        b.putShort((short)1).putShort((short)channels).putInt(22050);
        b.putInt(22050*channels*2).putShort((short)(2*channels)).putShort((short)16);
        b.put("data".getBytes(StandardCharsets.US_ASCII)).putInt(0);
        return b.array();
    }
    public static void main(String[] args) throws Exception {
        Path tmp=Files.createTempDirectory("siegerradio-java-test");
        try {
            Path root=tmp.resolve("SiegerRadio");
            Path sounds=root.resolve("42/media/sound/SiegerRadio");
            Files.createDirectories(sounds);
            Files.write(sounds.resolve("north_track_01.wav"),pcm(2)); // real stereo WAV
            Files.write(sounds.resolve("north_track_41.wav"),pcm(1)); // current legacy mono WAV
            System.setProperty("radio.test.mod",root.toString());
            ok(SiegerRadioBridge.ready(),"Expected compatible mock Java FMOD API");
            ok(!SiegerRadioBridge.start("north_track_42",1000,true,1,2,0,.5),"Unknown track must fail");
            ok(!SiegerRadioBridge.start("../evil",1000,false,1,2,0,.5),"Traversal must fail");
            ok(!SiegerRadioBridge.start("north_track_02",1000,true,1,2,0,.5),"Missing PCM must fail");
            ok(!SiegerRadioBridge.start("north_track_01",720000,false,1,2,0,.5),"Out of range seek");
            ok(!SiegerRadioBridge.start("north_track_01",Double.NaN,false,1,2,0,.5),"NaN seek");
            ok(javafmod.created==0,"Rejected inputs must not call native audio");
            ok(SiegerRadioBridge.start("north_track_01",99000,true,100,200,0,.6),"Seeked world radio");
            ok(javafmod.created==1 && javafmod.started==1 && javafmod.position==99000,"Stream and seek");
            ok((javafmod.flags&0x80L)!=0 && (javafmod.flags&0x10L)!=0,
               "Must stream in native spatial mode");
            ok((javafmod.flags&0x08L)==0,"World radio must never use 2D mode");
            ok(javafmod.spreadCalls==1 && javafmod.spreadDegrees==0f,
               "Stereo 3D uses a single stream and initial zero degree spread");
            ok(javafmod.currentGroup==999 && javafmod.groupCreates==1 && !javafmod.paused,
                "One private stereo bus; native 3D source; paused setup before audio");
            ok(SiegerRadioBridge.details().contains("output=private_stereo_3d"),"Route diagnostic");
            ok(SiegerRadioBridge.setOutput("native") && javafmod.currentGroup==601,"Local native A/B route");
            ok(SiegerRadioBridge.setOutput("stereo") && javafmod.currentGroup==999,"Back to private stereo");
            ok(javafmod.started==1 && javafmod.seeks==1 && javafmod.groupCreates==1,
               "Route changes keep one channel, same position, no extra group");
            ok(!SiegerRadioBridge.setOutput("global"),"Reject arbitrary output control");
            ok(!SiegerRadioBridge.setSpread(17),"Reject arbitrary spread angles");
            ok(SiegerRadioBridge.setSpread(90),"Allow approved live stereo A/B preset");
            ok(javafmod.spreadCalls==2 && javafmod.spreadDegrees==90f
               && javafmod.started==1 && javafmod.seeks==1,
               "Changing width must not restart or seek another song");
            for (int degrees : new int[]{0,60,90,120}) {
                ok(SiegerRadioBridge.setSpread(degrees),"Live A/B width");
                ok(javafmod.spreadDegrees==degrees && javafmod.started==1
                   && javafmod.seeks==1,"A/B must retain one stream and offset");
            }
            ok(!SiegerRadioBridge.setSpread(Double.NaN),"Reject NaN audio controls");
            ok(javafmod.nearDistance==4f && javafmod.farDistance==12f,
               "World radio must be full-volume within four FMOD units, bounded to twelve");
            ok(javafmod.volume>.5 && javafmod.located>=1,"Native position and speaker gain");
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,0,.2),"Moving car update");
            int located=javafmod.located;
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,0,.2),"Unchanged source");
            ok(javafmod.located==located,"Static source must not re-enter JNI for identical position");
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,2,.2) && javafmod.z==6f,
               "Height uses the same three-units-per-level coordinate as PZ listener");
            ok(javafmod.volume<=.21,"Updated gain");
            ok(!SiegerRadioBridge.update("north_track_02",true,110,200,0,.2),"Wrong current ID");
            SiegerRadioBridge.stop(); SiegerRadioBridge.stop();
            ok(javafmod.stopped==1 && javafmod.released==1,"Exactly once release");
            ok(SiegerRadioBridge.start("north_track_41",25000,false,1,2,0,.7),"Portable stream");
            ok((javafmod.flags&0x08L)!=0 && (javafmod.flags&0x10L)==0,"Must use 2D for portable");
            ok(javafmod.position==25000,"Portable tune seeks immediately");
            ok(javafmod.spreadCalls==6,"Portable mono music must not use 3D spread");
            SiegerRadioBridge.stop();
            ok(SiegerRadioBridge.start("north_track_41",30000,true,10,20,0,.5),
               "Fallback legacy mono FMOD_3D must remain available");
            ok(javafmod.spreadCalls==6 &&
               "mono_3d_point".equals(SiegerRadioBridge.spatialStatus()),
               "A mono WAV cannot be passed off as stereo with 3D spread");
            SiegerRadioBridge.stop();
            ok(javafmod.stopped==3 && javafmod.released==3,"Clean last channel");
            ok(javafmod.groupCreates==javafmod.groupReleases,"All private groups freed");
            System.out.println("PASS: Java bounded FMOD streaming, local file validation, seek, modes, cleanup");
        } finally {
            // Test sandbox only: remove files created by the harness.
            Path root=tmp.resolve("SiegerRadio/42/media/sound/SiegerRadio");
            Files.deleteIfExists(root.resolve("north_track_01.wav"));
            Files.deleteIfExists(root.resolve("north_track_41.wav"));
        }
    }
}

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
            ok("radio-pan11".equals(SiegerRadioBridge.build()),"Native build attestation must match Lua");
            ok(!SiegerRadioBridge.start("north_track_42",1000,true,1,2,0,.5,false),"Unknown track must fail");
            ok(!SiegerRadioBridge.start("../evil",1000,false,1,2,0,.5,false),"Traversal must fail");
            ok(!SiegerRadioBridge.start("north_track_02",1000,true,1,2,0,.5,false),"Missing PCM must fail");
            ok(!SiegerRadioBridge.start("north_track_01",720000,false,1,2,0,.5,false),"Out of range seek");
            ok(!SiegerRadioBridge.start("north_track_01",Double.NaN,false,1,2,0,.5,false),"NaN seek");
            ok(javafmod.created==0,"Rejected inputs must not call native audio");
            ok(SiegerRadioBridge.start("north_track_01",99000,true,100,200,0,.6,false),"Seeked world radio");
            ok(javafmod.created==1 && javafmod.started==1 && javafmod.position==99000,"Stream and seek");
            ok((javafmod.flags&0x80L)!=0 && (javafmod.flags&0x10L)!=0,
               "Must stream in native spatial mode");
            ok((javafmod.flags&0x08L)==0,"World radio must never use 2D mode");
            ok(javafmod.spreadCalls==1 && javafmod.spreadDegrees==0f,
               "Stereo 3D uses a single stream and initial zero degree spread");
            ok(javafmod.currentGroup==999 && javafmod.groupCreates==1 && !javafmod.paused,
                "One private stereo bus; native 3D source; paused setup before audio");
            ok(SiegerRadioBridge.details().contains("output=private_stereo_3d"),"Route diagnostic");
            ok(javafmod.priorityCalls==1&&javafmod.lastPriority==32,"One local priority update per stream");
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
            ok(!SiegerRadioBridge.setCabin(true) && javafmod.panLevel==1f,
               "World furniture must refuse in-car panorama control");
            ok(javafmod.nearDistance>3.7f && javafmod.nearDistance<4f
               && javafmod.farDistance>11f && javafmod.farDistance<12f,
               "Furniture FMOD radius at gain .6 scales below the full 4/12");
            ok(javafmod.volume>.5 && javafmod.located>=1,"Native position and speaker gain");
            int previousRangeCalls=javafmod.rangeCalls;
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,0,.2,true),
               "Changing from furniture to car keeps one stream");
            ok(javafmod.nearDistance>2f && javafmod.nearDistance<3f
               && javafmod.farDistance>13f && javafmod.farDistance<14f
               && javafmod.rangeCalls==previousRangeCalls+1,
               "Quiet car must have volume-dependent radius, not a fixed 30");
            int cabinCalls=javafmod.spreadCalls,panCalls=javafmod.panCalls;
            ok(SiegerRadioBridge.setCabin(true)&&javafmod.spreadDegrees==30f
               && javafmod.panLevel==.30f,"Occupied car retains one 3D source with soft central pan");
            ok(SiegerRadioBridge.details().contains("cabin_pan=cabin_30pct_3d"),
               "Diagnostics must state active cabin blend, not claim untested headphone result");
            ok(SiegerRadioBridge.setCabin(true)&&javafmod.spreadCalls==cabinCalls+1
               && javafmod.panCalls==panCalls+1,"Identical cabin tick must not repeat JNI");
            ok(SiegerRadioBridge.setCabin(false)&&javafmod.spreadDegrees==120f
               && javafmod.panLevel==1f,"Exit MUST restore fully directional exterior");
            ok(javafmod.started==1&&javafmod.seeks==1,"Cabin changes retain same stream/timeline");
            int located=javafmod.located;
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,0,.2,true),"Unchanged car source");
            ok(javafmod.located==located,"Static source must not re-enter JNI for identical position");
            ok(javafmod.rangeCalls==previousRangeCalls+1,
               "Same gain/kind must not repeat minMax JNI");
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,2,.2,true) && javafmod.z==6f,
               "Height uses the same three-units-per-level coordinate as PZ listener");
            ok(javafmod.volume<=.21,"Updated gain");
            int priorLevelCalls=javafmod.panCalls;
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,2,.65,true)
               && Math.abs(javafmod.farDistance-30f)<.0001f
               && Math.abs(javafmod.nearDistance-4.8f)<.0001f,
               "Increasing the SAME car radio to 100% must restore 4.8/30");
            ok(javafmod.panCalls==priorLevelCalls,"Volume updates cannot change cabin panning");
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,2,.065,true)
               && Math.abs(javafmod.farDistance-8.4f)<.001f,
               "Ten percent device volume -> 8.4-cell car FMOD reach");
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,2,.65,false)
               && Math.abs(javafmod.nearDistance-4f)<.0001f
               && Math.abs(javafmod.farDistance-12f)<.0001f,
               "Full-volume furniture restores 4/12 without stopping channel");
            ok(javafmod.started==1 && javafmod.seeks==1,
               "Range updates must never create or seek another stream");
            ok(!SiegerRadioBridge.start("north_track_01",1000,false,1,2,0,.5,true),
               "A vehicle source cannot use non-spatial FMOD_2D");
            ok(!SiegerRadioBridge.update("north_track_02",true,110,200,0,.2,false),"Wrong current ID");
            SiegerRadioBridge.stop(); SiegerRadioBridge.stop();
            ok(javafmod.stopped==1 && javafmod.released==1,"Exactly once release");
            ok(SiegerRadioBridge.start("north_track_41",25000,false,1,2,0,.7,false),"Portable stream");
            ok((javafmod.flags&0x08L)!=0 && (javafmod.flags&0x10L)==0,"Must use 2D for portable");
            ok(javafmod.position==25000,"Portable tune seeks immediately");
            ok(javafmod.spreadCalls==8 && javafmod.panLevel==1f,
               "Portable mono music must remain 2D; never apply cabin pan");
            SiegerRadioBridge.stop();
            ok(SiegerRadioBridge.start("north_track_41",30000,true,10,20,0,.5,true),
               "Fallback legacy mono FMOD_3D must remain available");
            ok(javafmod.spreadCalls==8 &&
               javafmod.nearDistance>3f && javafmod.farDistance>24f
               && javafmod.panLevel==1f &&
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

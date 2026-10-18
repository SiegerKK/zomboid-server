import java.nio.file.*;
import siegerradio.bridge.SiegerRadioBridge;
import fmod.javafmod;
public final class SiegerRadioBridgeTest {
    private static void ok(boolean value,String reason) {if(!value)throw new AssertionError(reason);}
    public static void main(String[] args) throws Exception {
        Path tmp=Files.createTempDirectory("siegerradio-java-test");
        try {
            Path root=tmp.resolve("SiegerRadio");
            Path sounds=root.resolve("42/media/sound/SiegerRadio");
            Files.createDirectories(sounds);
            Files.write(sounds.resolve("north_track_01.wav"),new byte[]{82,73,70,70});
            Files.write(sounds.resolve("north_track_41.wav"),new byte[]{82,73,70,70});
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
            ok(javafmod.nearDistance==4f && javafmod.farDistance==12f,
               "World radio must be full-volume within four FMOD units, bounded to twelve");
            ok(javafmod.volume>.5 && javafmod.located>=1,"Native position and speaker gain");
            ok(SiegerRadioBridge.update("north_track_01",true,110,200,0,.2),"Moving car update");
            ok(javafmod.volume<=.21,"Updated gain");
            ok(!SiegerRadioBridge.update("north_track_02",true,110,200,0,.2),"Wrong current ID");
            SiegerRadioBridge.stop(); SiegerRadioBridge.stop();
            ok(javafmod.stopped==1 && javafmod.released==1,"Exactly once release");
            ok(SiegerRadioBridge.start("north_track_41",25000,false,1,2,0,.7),"Portable stream");
            ok((javafmod.flags&0x08L)!=0 && (javafmod.flags&0x10L)==0,"Must use 2D for portable");
            ok(javafmod.position==25000,"Portable tune seeks immediately");
            SiegerRadioBridge.stop();
            ok(javafmod.stopped==2 && javafmod.released==2,"Clean last channel");
            System.out.println("PASS: Java bounded FMOD streaming, local file validation, seek, modes, cleanup");
        } finally {
            // Test sandbox only: remove files created by the harness.
            Path root=tmp.resolve("SiegerRadio/42/media/sound/SiegerRadio");
            Files.deleteIfExists(root.resolve("north_track_01.wav"));
            Files.deleteIfExists(root.resolve("north_track_41.wav"));
        }
    }
}

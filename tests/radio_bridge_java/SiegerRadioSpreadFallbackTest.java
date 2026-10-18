import java.nio.file.*;
import java.nio.*;
import siegerradio.bridge.SiegerRadioBridge;
import fmod.javafmod;
/** Mock failure isolation only; never an audible game acceptance. */
public class SiegerRadioSpreadFallbackTest {
    public static void main(String[] args) throws Exception {
        Path root=Files.createTempDirectory("radio-spread-fallback");
        Path audio=root.resolve("42/media/sound/SiegerRadio/north_track_38.wav");
        Files.createDirectories(audio.getParent());
        ByteBuffer b=ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN);
        b.put("RIFF".getBytes()).putInt(36).put("WAVEfmt ".getBytes()).putInt(16);
        b.putShort((short)1).putShort((short)2).putInt(22050).putInt(88200);
        b.putShort((short)4).putShort((short)16).put("data".getBytes()).putInt(0);
        Files.write(audio,b.array());System.setProperty("radio.test.mod",root.toString());
        if(!SiegerRadioBridge.start("north_track_38",18000,true,100,200,0,.5))
            throw new AssertionError("Optional spread failure must retain FMOD_3D");
        if(!SiegerRadioBridge.spatialStatus().equals(args[0]))throw new AssertionError("Status");
        if(SiegerRadioBridge.setSpread(60))throw new AssertionError("Must report failure");
        if(javafmod.started!=1||javafmod.seeks!=1||(javafmod.flags&0x10)==0
           ||(javafmod.flags&0x08)!=0)throw new AssertionError("One genuine 3D stream");
        SiegerRadioBridge.stop();
        if(javafmod.stopped!=1||javafmod.released!=1)throw new AssertionError("Cleanup");
        Files.delete(audio);
        System.out.println("PASS: optional spread "+args[0]+" retains one working 3D stream");
    }
}

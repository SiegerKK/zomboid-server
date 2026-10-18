package siegerradio.bridge;

import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Locale;
import se.krka.kahlua.integration.annotations.LuaMethod;

/**
 * Client-only FMOD bridge, restricted to the signed-off NORTHBOUND local WAV
 * allowlist. No server/network/file-writing API and no bytecode game patches.
 *
 * The PZ javafmod ABI is resolved at runtime to refuse incompatible builds.
 * An actual two-client B42.21 acceptance is REQUIRED before distribution.
 */
public final class SiegerRadioBridge {
    private static final long FMOD_CREATESTREAM = 0x80L;
    private static final long FMOD_2D = 0x08L;
    private static final long FMOD_3D = 0x10L;
    private static final float MAX_VOLUME = 0.70f;
    // FMOD rolloff follows the same current-volume curve as the Lua receiver.
    // At V=1 retain old near/far endpoints: 4/12 furniture; 4.8/30 vehicle.
    private static final float GAIN_AT_FULL_DEVICE_VOLUME=0.65f;
    private static final float FURNITURE_MIN_NEAR=1.2f, FURNITURE_NEAR_SPAN=2.8f;
    private static final float FURNITURE_MIN_FAR=3f, FURNITURE_FAR_SPAN=9f;
    private static final float VEHICLE_MIN_NEAR=1.4f, VEHICLE_NEAR_SPAN=3.4f;
    private static final float VEHICLE_MIN_FAR=6f, VEHICLE_FAR_SPAN=24f;
    private static final int LAST_TRACK = 41;
    private static final int MAX_MS = 720_000;
    private static final long MAX_WAV_BYTES = 32L * 1024 * 1024;

    private static Method create, play, seek, volume, channelStop, soundRelease, pause;
    private static Method set3d, minMax, spread, level3d;
    // A physical radio is one point, not two phantom speakers 120 degrees apart.
    private static float stereoSpreadDegrees = 0f;
    private static boolean sourceStereo;
    private static Method createGroup, getGroupDsp, setFormat, setGroup, getGroup, releaseGroup, memoryAddress;
    private static ByteBuffer pointerSlot;
    private static long stereoGroup, originalGroup;
    private static boolean stereoOutput = true;
    private static String outputStatus = "idle";
    private static float previousX, previousY, previousZ, previousGain, previousNear, previousFar;

    // One audible music voice should not lose its slot to default-priority ambience.
    // Local channel only; never raises the global software-channel limit.
    private static Method priority;
    private static String priorityStatus="idle";
    private static final int MUSIC_PRIORITY=32;
    private static boolean cabin;
    // Position remains the single real FMOD_3D car radio. Its cabin channel
    // has mild 25% spatial panning plus centered stereo; exterior stays 100% 3D.
    private static final float CABIN_SPREAD=20f;
    private static final float FALLBACK_CABIN_SPREAD=60f;
    private static final float CABIN_3D_LEVEL=0.25f;
    private static String cabinPanStatus="idle";

    private static String spatialStatus = "idle";
    private static boolean bound;
    private static String boundApi="unbound";
    private static String failure = "not_probed";
    private static long soundHandle, channelHandle;
    private static String playingId;
    private static boolean playing3d;
    private static boolean vehicleSource;

    private SiegerRadioBridge() {}

    private static Method required(Class<?> api, String name, Class<?>... types)
            throws ReflectiveOperationException {
        Method method = api.getMethod(name, types);
        if (!Modifier.isStatic(method.getModifiers())) throw new NoSuchMethodException(name);
        return method;
    }

    private static Method optionalSpatial(String primary, String method) {
        for(String apiName:new String[]{primary,"fmod.javafmodJNI"}) {
            try {
                Method m=required(Class.forName(apiName),method,long.class,float.class);
                if(m.getReturnType()==int.class)return m;
            } catch(ReflectiveOperationException | LinkageError unsupported) {
                // Typed SWIG wrappers are not a verified JNI ABI.
            }
        }
        return null;
    }

    private static boolean bind() {
        if (bound) return true;
        // Some pinned builds expose high-level wrappers, some only JNI.
        // Select one complete matching ABI, never mix methods from both.
        for (String className : new String[]{"fmod.javafmod", "fmod.javafmodJNI"}) {
            try {
                Class<?> api = Class.forName(className);
                Method c = required(api, "FMOD_System_CreateSound", String.class, long.class);
                Method p = required(api, "FMOD_System_PlaySound", long.class, long.class);
                Method sk = required(api, "FMOD_Channel_SetPosition", long.class, long.class);
                Method v = required(api, "FMOD_Channel_SetVolume", long.class, float.class);
                Method st = required(api, "FMOD_Channel_Stop", long.class);
                Method pa = required(api, "FMOD_Channel_SetPaused", long.class, long.class);
                Method rel = required(api, "FMOD_Sound_Release", long.class);
                Method attrs = required(api, "FMOD_Channel_Set3DAttributes", long.class,
                                  float.class,float.class,float.class,
                                  float.class,float.class,float.class);
                Method range = required(api, "FMOD_Channel_Set3DMinMaxDistance",
                                        long.class,float.class,float.class);
                if (c.getReturnType()!=long.class || p.getReturnType()!=long.class
                    || sk.getReturnType()!=int.class || v.getReturnType()!=int.class
                    || st.getReturnType()!=int.class || pa.getReturnType()!=int.class || rel.getReturnType()!=int.class
                    || attrs.getReturnType()!=int.class || range.getReturnType()!=int.class)
                    continue;
                create=c;play=p;seek=sk;volume=v;channelStop=st;soundRelease=rel;
                set3d=attrs;minMax=range;pause=pa;
                // Optional: the native JNI spread method differs by game build.
                // Missing support must never turn the radio into a 2D sound.
                spread=optionalSpatial(className,"FMOD_Channel_Set3DSpread");
                // Some PZ versions expose long,float Set3DLevel only in
                // javafmodJNI. Verify the EXACT method ABI, no SWIG guessing.
                // Core streaming remains pinned to one Java FMOD API.
                level3d=optionalSpatial(className,"FMOD_Channel_Set3DLevel");
                // Optional PRIVATE stereo bus, never a device/listener/global-format patch.
                // Output pointers are confined to ONE owned 8-byte direct buffer.
                createGroup=null;
                try {
                    Method cg=required(api,"FMOD_System_CreateChannelGroup",String.class);
                    Method gd=required(api,"FMOD_ChannelGroup_GetDSP",long.class,int.class,long.class);
                    Method sf=required(api,"FMOD_DSP_SetChannelFormat",long.class,long.class,int.class,long.class);
                    Method sg=required(api,"FMOD_Channel_SetChannelGroup",long.class,long.class);
                    Method gg=required(api,"FMOD_Channel_GetChannelGroup",long.class,long.class);
                    Method rg=required(api,"FMOD_ChannelGroup_Release",long.class);
                    if(cg.getReturnType()!=long.class || gd.getReturnType()!=int.class
                        || sf.getReturnType()!=int.class || sg.getReturnType()!=int.class
                        || gg.getReturnType()!=int.class || rg.getReturnType()!=int.class)
                        throw new NoSuchMethodException("Private bus ABI");
                    Method ma=Class.forName("org.lwjgl.system.MemoryUtil").getMethod("memAddress",ByteBuffer.class);
                    if(ma.getReturnType()!=long.class || !Modifier.isStatic(ma.getModifiers()))
                        throw new NoSuchMethodException("Direct-buffer address ABI");
                    pointerSlot=ByteBuffer.allocateDirect(Long.BYTES).order(ByteOrder.nativeOrder());
                    memoryAddress=ma;getGroupDsp=gd;setFormat=sf;setGroup=sg;getGroup=gg;releaseGroup=rg;createGroup=cg;
                } catch (ReflectiveOperationException | LinkageError unavailable) {
                    createGroup=null; // ordinary native 3D remains available, status says unavailable
                }
                priority=null;
                try {
                    Method pr=required(api,"FMOD_Channel_SetPriority",long.class,int.class);
                    if(pr.getReturnType()==int.class)priority=pr;
                } catch(ReflectiveOperationException unavailable) { /* optional ABI */ }
                bound=true;boundApi=className;failure="ready";
                return true;
            } catch (ReflectiveOperationException | LinkageError unavailable) {
                // No fallback to unverified invocation or eager PCM playback.
            }
        }
        failure="unsupported_build";
        return false;
    }

    private static long handle(Method method, Object... arguments) throws Exception {
        return ((Number) method.invoke(null, arguments)).longValue();
    }

    private static void check(Method method, Object... arguments) throws Exception {
        if (((Number) method.invoke(null, arguments)).intValue() != 0)
            throw new IllegalStateException("FMOD call failed: " + method.getName());
    }

    private static boolean finite(double value) {
        return !Double.isNaN(value) && !Double.isInfinite(value);
    }

    private static boolean validPosition(double x, double y, double z) {
        return finite(x) && finite(y) && finite(z)
            && x >= 0 && x <= 200_000 && y >= 0 && y <= 200_000
            && z >= 0 && z <= 32;
    }

    private static boolean validTrack(String id) {
        if (id == null || !id.matches("north_track_[0-9]{2}")) return false;
        int n = Integer.parseInt(id.substring("north_track_".length()));
        return n >= 1 && n <= LAST_TRACK;
    }

    // Prefer the exact loaded PZ mod directory, including Workshop installs.
    private static Path modRoot() throws Exception {
        Class<?> fs = Class.forName("zombie.ZomboidFileSystem");
        Field singleton = fs.getField("instance");
        Object instance = singleton.get(null);
        if (instance == null) throw new IllegalStateException("No loaded mod index");
        Method modDir = fs.getMethod("getModDir", String.class);
        Object value = modDir.invoke(instance, "SiegerRadio");
        if (!(value instanceof String) || ((String) value).isBlank()) {
            throw new IllegalStateException("SiegerRadio mod not enabled");
        }
        Path root = Paths.get((String) value).toRealPath();
        if (!Files.isDirectory(root) || Files.isSymbolicLink(root))
            throw new IllegalStateException("Unsafe mod directory");
        return root;
    }

    private static Path reviewedAudioFile(String trackId) throws Exception {
        Path root = modRoot();
        // PZ getModDir may refer to either <mod> or <mod>/42.
        Path[] media = { root.resolve("42/media"), root.resolve("media") };
        for (Path dir : media) {
            Path location = dir.resolve("sound/SiegerRadio/" + trackId + ".wav").normalize();
            if (!location.startsWith(root) || !Files.isRegularFile(location)
                || Files.isSymbolicLink(location) || Files.size(location) > MAX_WAV_BYTES)
                continue;
            Path real = location.toRealPath();
            if (real.startsWith(root) && real.toString().toLowerCase(Locale.ROOT).endsWith(".wav"))
                return real;
        }
        throw new IllegalStateException("Registered local PCM absent: " + trackId);
    }

    /**
     * Read only the first bounded RIFF/WAVE chunks, not the PCM payload.
     * A stereo-only spread profile must NEVER be faked by duplicating mono.
     */
    private static int pcmChannels(Path file) throws IOException {
        try (InputStream raw = new BufferedInputStream(Files.newInputStream(file));
             DataInputStream input = new DataInputStream(raw)) {
            byte[] header=new byte[12]; input.readFully(header);
            if (header[0]!='R'||header[1]!='I'||header[2]!='F'||header[3]!='F'
                ||header[8]!='W'||header[9]!='A'||header[10]!='V'||header[11]!='E')
                throw new IOException("Not RIFF/WAVE");
            for(int chunk=0;chunk<24;chunk++) {
                byte[] label=new byte[4]; input.readFully(label);
                int length=Integer.reverseBytes(input.readInt());
                if(length<0||length>65536)throw new IOException("Invalid WAV header");
                if(label[0]=='f'&&label[1]=='m'&&label[2]=='t'&&label[3]==' ') {
                    if(length<16)throw new IOException("Short fmt chunk");
                    byte[] fmt=new byte[16];input.readFully(fmt);
                    int codec=(fmt[0]&255)|((fmt[1]&255)<<8);
                    int channels=(fmt[2]&255)|((fmt[3]&255)<<8);
                    long rate=(fmt[4]&255L)|((fmt[5]&255L)<<8)
                             |((fmt[6]&255L)<<16)|((fmt[7]&255L)<<24);
                    int bits=(fmt[14]&255)|((fmt[15]&255)<<8);
                    if(codec!=1||(channels!=1&&channels!=2)||rate!=22050L||bits!=16)
                        throw new IOException("Unsupported PCM");
                    return channels;
                }
                input.skipNBytes(length+(length&1));
            }
            throw new IOException("Missing PCM format");
        }
    }

    private static boolean approvedSpread(double angle) {
        return angle==0||angle==60||angle==90||angle==120||angle==150||angle==180;
    }

    private static boolean applyStereoSpread(float degrees) {
        if(spread==null||channelHandle==0) {
            spatialStatus="stereo_3d_spread_unavailable";
            return false;
        }
        try {
            check(spread,channelHandle,degrees);
            spatialStatus="stereo_3d_spread_"+(int)degrees;
            return true;
        } catch (Exception | LinkageError error) {
            spatialStatus="stereo_3d_spread_failed";
            return false; // Optional; do not end playback or restart audio.
        }
    }

    /** Owner-only local 3D A/B preset: adjusts the same active channel. */
    @LuaMethod(name = "siegradioBridgeSetSpread", global = true)
    public static synchronized boolean setSpread(double requested) {
        if(!approvedSpread(requested))return false;
        float degrees=(float)requested;
        if(channelHandle!=0&&playing3d&&sourceStereo) {
            if(!applyStereoSpread(cabin?CABIN_SPREAD:degrees))return false;
        }
        stereoSpreadDegrees=degrees;
        return spread!=null;
    }

    private static boolean applyCabinPan(float value) {
        if(level3d==null) {cabinPanStatus="unavailable";return false;}
        try {
            check(level3d,channelHandle,value);
            cabinPanStatus=value==1f?"exterior_full_3d":"cabin_25pct_3d";
            return true;
        } catch(Exception|LinkageError error) {
            cabinPanStatus="failed";return false;
        }
    }

    /** Mix centered stereo with real 3D pan for an occupant of THIS car.
     * No 2D duplicate, no camera-relative relocation and no other channel.
     */
    @LuaMethod(name="siegradioBridgeSetCabin",global=true)
    public static synchronized boolean setCabin(boolean inside) {
        if(channelHandle==0||!playing3d||!sourceStereo)return false;
        // Only actual vehicle music is eligible: a nearby furniture source
        // can NEVER be recentered through the cabin API.
        if(inside&&!vehicleSource)return false;
        if(cabin==inside)return true;
        boolean panOk=applyCabinPan(inside?CABIN_3D_LEVEL:1f);
        // Preserve previous mild cabin stereo when optional 3DLevel fails.
        boolean spreadOk=applyStereoSpread(inside
            ?(panOk?CABIN_SPREAD:FALLBACK_CABIN_SPREAD):stereoSpreadDegrees);
        if(!panOk&&!spreadOk)return false;
        cabin=inside;
        return true;
    }

    @LuaMethod(name = "siegradioBridgeSpatialStatus", global = true)
    public static synchronized String spatialStatus() { return spatialStatus; }

    private static long outputPointer(Method getter, Object... leading) throws Exception {
        pointerSlot.putLong(0,0L);
        long address=((Number)memoryAddress.invoke(null,pointerSlot)).longValue();
        if(address==0)throw new IllegalStateException("Missing direct buffer address");
        Object[] args=new Object[leading.length+1];
        System.arraycopy(leading,0,args,0,leading.length);args[leading.length]=address;
        check(getter,args);
        long result=pointerSlot.getLong(0);
        if(result==0)throw new IllegalStateException("No native group/DSP handle");
        return result;
    }

    private static boolean routeOutput() {
        if(channelHandle==0||!playing3d)return false;
        if(!stereoOutput) {
            try {
                if(stereoGroup!=0) {
                    check(setGroup,channelHandle,originalGroup);
                }
                outputStatus="native_3d";return true;
            } catch(Exception|LinkageError error) {outputStatus="native_route_failed";return false;}
        }
        if(createGroup==null) {outputStatus="stereo_bus_unavailable";return false;}
        if(stereoGroup!=0) {
            try {check(setGroup,channelHandle,stereoGroup);outputStatus="private_stereo_3d";return true;}
            catch(Exception|LinkageError error) {outputStatus="stereo_route_failed";return false;}
        }
        try {
            originalGroup=outputPointer(getGroup,channelHandle);
            stereoGroup=handle(createGroup,"SiegerRadioStereo");
            if(stereoGroup==0)throw new IllegalStateException("No private bus");
            long fader=outputPointer(getGroupDsp,stereoGroup,-2); // FMOD_CHANNELCONTROL_DSP_FADER
            // FL|FR=3, two channels, FMOD_SPEAKERMODE_STEREO=3. Only OUR fader.
            // The legacy JNI wraps mask/mode as POINTERS to 32-bit enums,
            // despite both Java arguments being long. Never pass literal 3.
            long address=((Number)memoryAddress.invoke(null,pointerSlot)).longValue();
            if(address==0)throw new IllegalStateException("Missing owned enum buffer");
            pointerSlot.putInt(0,3);pointerSlot.putInt(4,3);
            check(setFormat,fader,address,2,address+4);
            check(setGroup,channelHandle,stereoGroup);
            outputStatus="private_stereo_3d";return true;
        } catch(Exception|LinkageError error) {
            // The channel stays on its native group when optional setup fails.
            // Restore before releasing a possibly attached group.
            if(stereoGroup!=0) {
                try {check(setGroup,channelHandle,originalGroup);check(releaseGroup,stereoGroup);stereoGroup=0;}
                catch(Exception|LinkageError cleanup) { /* retained for stopInternal */ }
            }
            outputStatus="stereo_bus_failed";return false;
        }
    }

    @LuaMethod(name="siegradioBridgeSetOutput",global=true)
    public static synchronized boolean setOutput(String profile) {
        if(!"stereo".equals(profile)&&!"native".equals(profile))return false;
        stereoOutput="stereo".equals(profile);
        if(channelHandle!=0&&playing3d)return routeOutput();
        return true;
    }

    /** Bounded, local diagnostic: no device changes, paths or world positions. */
    @LuaMethod(name = "siegradioBridgeDetails", global = true)
    public static synchronized String details() {
        return "api="+boundApi+" active="+(channelHandle!=0)
            +" stereo="+sourceStereo+" spatial="+playing3d
            +" spread_api="+(spread!=null)+" requested="+(int)stereoSpreadDegrees
            +" cabin="+cabin+" cabin_pan="+cabinPanStatus
            +" output="+outputStatus+" status="+spatialStatus+" priority="+priorityStatus
            +" near="+previousNear+" far="+previousFar;
    }

    private static void applyPriority() {
        priorityStatus="unavailable";
        if(priority==null)return;
        try {check(priority,channelHandle,MUSIC_PRIORITY);priorityStatus="32";}
        catch(Exception|LinkageError unavailable) {priorityStatus="failed";}
    }

    private static void stopInternal() {
        // Always drop handles exactly once and in dependency order.
        long channel = channelHandle, sound = soundHandle, group=stereoGroup;
        stereoGroup=0;originalGroup=0;outputStatus="idle";
        channelHandle = 0;
        soundHandle = 0;
        playingId = null;
        sourceStereo=false;
        playing3d=false;
        vehicleSource=false;
        spatialStatus="idle";priorityStatus="idle";cabin=false;cabinPanStatus="idle";
        previousNear=0f;previousFar=0f;
        if (channel != 0 && channelStop != null) {
            try { channelStop.invoke(null, channel); } catch (Throwable ignored) {}
        }
        if(group!=0&&releaseGroup!=null) {
            try {releaseGroup.invoke(null,group);} catch(Throwable ignored) {}
        }
        if (sound != 0 && soundRelease != null) {
            try { soundRelease.invoke(null, sound); } catch (Throwable ignored) {}
        }
    }

    @LuaMethod(name = "siegradioBridgeReady", global = true)
    public static synchronized boolean ready() {
        if (!bind()) return false;
        try { modRoot(); return true; }
        catch (Exception error) { failure = "mod_directory_unavailable"; return false; }
    }

    @LuaMethod(name = "siegradioBridgeStatus", global = true)
    public static synchronized String status() { return failure; }
    private static final String BRIDGE_BUILD = "radio-ops13";
    @LuaMethod(name = "siegradioBridgeBuild", global = true)
    public static String build() { return BRIDGE_BUILD; }

    @LuaMethod(name = "siegradioBridgeStop", global = true)
    public static synchronized void stop() { stopInternal(); }

    private static float deviceSliderFromGain(double gain) {
        return (float)Math.max(0.0,Math.min(1.0,gain/GAIN_AT_FULL_DEVICE_VOLUME));
    }

    private static float[] musicDistances(boolean vehicle,double gain) {
        float v=deviceSliderFromGain(gain);
        return vehicle
            ?new float[]{VEHICLE_MIN_NEAR+VEHICLE_NEAR_SPAN*v,VEHICLE_MIN_FAR+VEHICLE_FAR_SPAN*v}
            :new float[]{FURNITURE_MIN_NEAR+FURNITURE_NEAR_SPAN*v,FURNITURE_MIN_FAR+FURNITURE_FAR_SPAN*v};
    }

    private static void applyMusicDistances(boolean vehicle,double gain) throws Exception {
        float[] distances=musicDistances(vehicle,gain);
        if(previousNear!=distances[0]||previousFar!=distances[1]) {
            check(minMax,channelHandle,distances[0],distances[1]);
            previousNear=distances[0];previousFar=distances[1];
        }
    }

    /**
     * Offset is a server-derived position in milliseconds, NOT an index into
     * an untrusted filename or arbitrary Java class. No stream when inaudible.
     */
    @LuaMethod(name = "siegradioBridgePlay", global = true)
    public static synchronized boolean start(String trackId, double offsetMs,
                                              boolean spatial, double x, double y, double z,
                                              double gain, boolean vehicle) {
        if (!bind() || (vehicle && !spatial) || !validTrack(trackId) || !finite(offsetMs)
            || offsetMs < 0 || offsetMs >= MAX_MS || !validPosition(x,y,z)
            || !finite(gain) || gain <= 0 || gain > 1) return false;
        stopInternal();
        try {
            Path path = reviewedAudioFile(trackId);
            int channels=pcmChannels(path);
            long flags = FMOD_CREATESTREAM | (spatial ? FMOD_3D : FMOD_2D);
            soundHandle = handle(create, path.toString(), flags);
            if (soundHandle == 0) throw new IllegalStateException("FMOD stream not created");
            channelHandle = handle(play, soundHandle, 1L); // JNI second argument is PAUSED, not a group
            if (channelHandle == 0) throw new IllegalStateException("FMOD channel not created");
            applyPriority();
            check(volume, channelHandle, 0.0f); // paused until route, source and seek are ready
            playing3d=spatial;
            if (spatial) {
                routeOutput(); // optional failure retains normal 3D and a diagnostic status
                applyMusicDistances(vehicle,gain);
                check(set3d, channelHandle, (float)x, (float)y, (float)z*3f, 0.0f, 0.0f, 0.0f);
                spatialStatus=channels==1?"mono_3d_point":"stereo_3d_point";
                if(channels==2)applyStereoSpread(stereoSpreadDegrees);
            } else spatialStatus="portable_2d";
            check(seek, channelHandle, (long)Math.floor(offsetMs));
            check(volume, channelHandle, (float)Math.min(MAX_VOLUME, gain));
            previousX=(float)x;previousY=(float)y;previousZ=(float)z*3f;
            previousGain=(float)Math.min(MAX_VOLUME,gain);
            check(pause,channelHandle,0L);
            playingId = trackId;
            playing3d = spatial;
            vehicleSource = vehicle;
            sourceStereo = channels==2;
            failure = "ready";
            return true;
        } catch (Exception | LinkageError error) {
            failure = "native_stream_start_failed";
            stopInternal();
            return false;
        }
    }

    @LuaMethod(name = "siegradioBridgeUpdate", global = true)
    public static synchronized boolean update(String trackId, boolean spatial,
                                               double x, double y, double z, double gain,
                                               boolean vehicle) {
        if ((vehicle && !spatial) || !validTrack(trackId) || channelHandle == 0 || !trackId.equals(playingId)
            || spatial != playing3d || !validPosition(x,y,z)
            || !finite(gain) || gain < 0 || gain > 1) return false;
        try {
            // Slider AND source type affect the native 3D rolloff in place.
            if(spatial) applyMusicDistances(vehicle,gain);
            vehicleSource=vehicle;
            float px=(float)x,py=(float)y,pz=(float)z*3f;
            if(spatial&&(px!=previousX||py!=previousY||pz!=previousZ)) {
                check(set3d,channelHandle,px,py,pz,0f,0f,0f);
                previousX=px;previousY=py;previousZ=pz;
            }
            float nextGain=(float)Math.min(MAX_VOLUME,gain);
            if(nextGain!=previousGain) {check(volume,channelHandle,nextGain);previousGain=nextGain;}
            return true;
        } catch (Exception | LinkageError error) {
            failure = "native_stream_update_failed";
            stopInternal();
            return false;
        }
    }

    @LuaMethod(name = "siegradioBridgeTrack", global = true)
    public static synchronized String track() { return playingId == null ? "" : playingId; }
}

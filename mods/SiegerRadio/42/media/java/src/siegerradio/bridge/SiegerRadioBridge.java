package siegerradio.bridge;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
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
    private static final int LAST_TRACK = 41;
    private static final int MAX_MS = 720_000;
    private static final long MAX_WAV_BYTES = 32L * 1024 * 1024;

    private static Method create, play, seek, volume, channelStop, soundRelease;
    private static Method set3d, minMax;
    private static boolean bound;
    private static String failure = "not_probed";
    private static long soundHandle, channelHandle;
    private static String playingId;
    private static boolean playing3d;

    private SiegerRadioBridge() {}

    private static Method required(Class<?> api, String name, Class<?>... types)
            throws ReflectiveOperationException {
        Method method = api.getMethod(name, types);
        if (!Modifier.isStatic(method.getModifiers())) throw new NoSuchMethodException(name);
        return method;
    }

    private static boolean bind() {
        if (bound) return true;
        try {
            // javafmod wraps PZ's installed FMOD integration; no custom DLLs.
            Class<?> api;
            try { api = Class.forName("fmod.javafmod"); }
            catch (ClassNotFoundException noWrapper) { api = Class.forName("fmod.javafmodJNI"); }
            create = required(api, "FMOD_System_CreateSound", String.class, long.class);
            play = required(api, "FMOD_System_PlaySound", long.class, long.class);
            seek = required(api, "FMOD_Channel_SetPosition", long.class, long.class);
            volume = required(api, "FMOD_Channel_SetVolume", long.class, float.class);
            channelStop = required(api, "FMOD_Channel_Stop", long.class);
            soundRelease = required(api, "FMOD_Sound_Release", long.class);
            set3d = required(api, "FMOD_Channel_Set3DAttributes", long.class,
                             float.class, float.class, float.class,
                             float.class, float.class, float.class);
            minMax = required(api, "FMOD_Channel_Set3DMinMaxDistance",
                              long.class, float.class, float.class);
            if (create.getReturnType() != long.class || play.getReturnType() != long.class
                || seek.getReturnType() != int.class || volume.getReturnType() != int.class
                || channelStop.getReturnType() != int.class
                || soundRelease.getReturnType() != int.class) {
                throw new NoSuchMethodException("Unexpected native return ABI");
            }
            bound = true;
            failure = "ready";
        } catch (ReflectiveOperationException | LinkageError error) {
            failure = "unsupported_build";
            bound = false;
        }
        return bound;
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

    private static void stopInternal() {
        // Always drop handles exactly once and in dependency order.
        long channel = channelHandle, sound = soundHandle;
        channelHandle = 0;
        soundHandle = 0;
        playingId = null;
        if (channel != 0 && channelStop != null) {
            try { channelStop.invoke(null, channel); } catch (Throwable ignored) {}
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

    @LuaMethod(name = "siegradioBridgeStop", global = true)
    public static synchronized void stop() { stopInternal(); }

    /**
     * Offset is a server-derived position in milliseconds, NOT an index into
     * an untrusted filename or arbitrary Java class. No stream when inaudible.
     */
    @LuaMethod(name = "siegradioBridgePlay", global = true)
    public static synchronized boolean start(String trackId, double offsetMs,
                                              boolean spatial, double x, double y, double z,
                                              double gain) {
        if (!bind() || !validTrack(trackId) || !finite(offsetMs)
            || offsetMs < 0 || offsetMs >= MAX_MS || !validPosition(x,y,z)
            || !finite(gain) || gain <= 0 || gain > 1) return false;
        stopInternal();
        try {
            Path path = reviewedAudioFile(trackId);
            long flags = FMOD_CREATESTREAM | (spatial ? FMOD_3D : FMOD_2D);
            soundHandle = handle(create, path.toString(), flags);
            if (soundHandle == 0) throw new IllegalStateException("FMOD stream not created");
            channelHandle = handle(play, soundHandle, 0L); // default master channel group
            if (channelHandle == 0) throw new IllegalStateException("FMOD channel not created");
            check(volume, channelHandle, 0.0f); // never leak a snippet from t=0
            if (spatial) {
                check(minMax, channelHandle, 1.0f, 12.0f);
                check(set3d, channelHandle, (float)x, (float)y, (float)z, 0.0f, 0.0f, 0.0f);
            }
            check(seek, channelHandle, (long)Math.floor(offsetMs));
            check(volume, channelHandle, (float)Math.min(MAX_VOLUME, gain));
            playingId = trackId;
            playing3d = spatial;
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
                                               double x, double y, double z, double gain) {
        if (!validTrack(trackId) || channelHandle == 0 || !trackId.equals(playingId)
            || spatial != playing3d || !validPosition(x,y,z)
            || !finite(gain) || gain < 0 || gain > 1) return false;
        try {
            if (spatial)
                check(set3d, channelHandle, (float)x, (float)y, (float)z, 0f,0f,0f);
            check(volume, channelHandle, (float)Math.min(MAX_VOLUME,gain));
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

package fmod;
public final class javafmod {
    public static long flags, position, channel, sound;
    public static float volume;
    public static int created, started, seeks, updated, stopped, released, located;
    public static long FMOD_System_CreateSound(String path, long mode) {
        if (!path.endsWith(".wav")) throw new AssertionError("Unsafe file extension");
        flags = mode; created++; sound = 900; return sound;
    }
    public static long FMOD_System_PlaySound(long ref, long group) {
        if (ref != sound || group != 0L) throw new AssertionError("Wrong FMOD sound or group");
        started++; channel = 800; return channel;
    }
    public static int FMOD_Channel_SetPosition(long ref, long millis) {
        if (ref != channel) throw new AssertionError("Wrong channel seek"); 
        position = millis; seeks++; return 0;
    }
    public static int FMOD_Channel_SetVolume(long ref, float v) {
        if (ref != channel) throw new AssertionError("Wrong channel volume");
        volume = v; updated++; return 0;
    }
    public static int FMOD_Channel_Stop(long ref) { stopped++; return 0; }
    public static int FMOD_Sound_Release(long ref) { released++; return 0; }
    public static int FMOD_Channel_Set3DAttributes(long ref, float x,float y,float z,
        float vx,float vy,float vz) { located++; return 0; }
    public static float nearDistance, farDistance, spreadDegrees;
    public static int spreadCalls;
    public static int FMOD_Channel_Set3DSpread(long ref,float degrees) {
        if(ref!=channel||degrees<0||degrees>180)
            throw new AssertionError("Spread outside approved 3D channel");
        spreadCalls++;
        spreadDegrees=degrees;
        return 0;
    }
    public static int FMOD_Channel_Set3DMinMaxDistance(long ref,float min,float max) {
        if (ref!=channel || min!=4f || max!=12f)
            throw new AssertionError("3D radio requires 4-tile full-volume near field and 12-tile maximum");
        nearDistance=min;
        farDistance=max;
        return 0;
    }
}

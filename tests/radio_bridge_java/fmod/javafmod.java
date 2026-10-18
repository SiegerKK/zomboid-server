package fmod;
public final class javafmod {
    public static long flags, position, channel, sound;
    public static float volume, x,y,z;
    public static boolean paused;
    public static long currentGroup=601;
    public static int groupCreates,groupReleases;
    public static int created, started, seeks, updated, stopped, released, located;
    public static long FMOD_System_CreateSound(String path, long mode) {
        if (!path.endsWith(".wav")) throw new AssertionError("Unsafe file extension");
        flags = mode; created++; sound = 900; return sound;
    }
    public static long FMOD_System_PlaySound(long ref, long pause) {
        if (ref != sound || pause != 1L) throw new AssertionError("JNI second argument must be paused=true");
        paused=true;currentGroup=601;
        started++; channel = 800; return channel;
    }
    public static int FMOD_Channel_SetPaused(long ref,long pause) {
        if(pause!=0L||seeks==0||volume<=0)throw new AssertionError("Unpause only after setup");
        paused=false;return 0;
    }
    public static long FMOD_System_CreateChannelGroup(String name) {
        if(!name.equals("SiegerRadioStereo"))throw new AssertionError("Private bus only");
        groupCreates++;return 999;
    }
    public static int FMOD_Channel_GetChannelGroup(long channel,long out) {
        org.lwjgl.system.MemoryUtil.buffer(out).putLong(0,currentGroup);return 0;
    }
    public static int FMOD_ChannelGroup_GetDSP(long group,int index,long out) {
        if(group!=999||index!=-2)throw new AssertionError("Owned fader only");
        if(Boolean.getBoolean("radio.test.busFails"))return 1;
        org.lwjgl.system.MemoryUtil.buffer(out).putLong(0,888);return 0;
    }
    public static int FMOD_DSP_SetChannelFormat(long dsp,long mask,int channels,long mode) {
        if(dsp!=888||mask!=1024||channels!=2||mode!=1028
            ||org.lwjgl.system.MemoryUtil.buffer(mask).getInt(0)!=3
            ||org.lwjgl.system.MemoryUtil.buffer(mask).getInt(4)!=3)throw new AssertionError("Owned stereo format only");
        return 0;
    }
    public static int FMOD_Channel_SetChannelGroup(long channel,long group) {
        if(channel!=800||(group!=601&&group!=999))throw new AssertionError("Only music channel routing");
        currentGroup=group;return 0;
    }
    public static int FMOD_ChannelGroup_Release(long group) {
        if(group!=999||currentGroup==999)throw new AssertionError("Release detached private group only");
        groupReleases++;return 0;
    }
    public static int priorityCalls,lastPriority;
    public static int FMOD_Channel_SetPriority(long ref,int value) {
        if(ref!=channel||value!=32)throw new AssertionError("Only owned music voice priority");
        if(Boolean.getBoolean("radio.test.priorityFails"))return 1;
        priorityCalls++;lastPriority=value;return 0;
    }
    public static int FMOD_Channel_SetPosition(long ref, long millis) {
        if (ref != channel) throw new AssertionError("Wrong channel seek"); 
        position = millis; seeks++; return 0;
    }
    public static int FMOD_Channel_SetVolume(long ref, float v) {
        if (ref != channel) throw new AssertionError("Wrong channel volume");
        volume = v; updated++; return 0;
    }
    public static int FMOD_Channel_Stop(long ref) { stopped++;currentGroup=0; return 0; }
    public static int FMOD_Sound_Release(long ref) { released++; return 0; }
    public static int FMOD_Channel_Set3DAttributes(long ref, float x,float y,float z,
        float vx,float vy,float vz) { javafmod.x=x;javafmod.y=y;javafmod.z=z;located++; return 0; }
    public static float nearDistance, farDistance, spreadDegrees;
    public static int spreadCalls;
    public static int FMOD_Channel_Set3DSpread(long ref,float degrees) {
        if(ref!=channel||degrees<0||degrees>180)
            throw new AssertionError("Spread outside approved 3D channel");
        if(Boolean.getBoolean("radio.test.spreadFails"))return 1;
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

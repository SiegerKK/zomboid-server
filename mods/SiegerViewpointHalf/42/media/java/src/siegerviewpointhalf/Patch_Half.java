package siegerviewpointhalf;

import me.zed_0xff.zombie_buddy.Patch;
import zombie.core.textures.*;
import zombie.core.utils.WrappedBuffer;
import java.nio.ByteBuffer;

public final class Patch_Half {
    private Patch_Half() {}
    @Patch(className="zombie.asset.FileTask_LoadPackImage",methodName="call",strictMatch=true)
    public static class Load {
        @Patch.OnExit public static void exit(@Patch.This Object task,
                @Patch.Return(readOnly=false) Object result) {
            result=HalfRuntime.adapt(task,result);
        }
    }
    @Patch(className="zombie.core.textures.TextureID",methodName="setImageData",strictMatch=true)
    public static class Remember {
        @Patch.OnEnter public static void enter(@Patch.This TextureID texture,
                @Patch.Argument(0) ImageData image) { HalfRuntime.remember(texture,image); }
    }
    @Patch(className="zombie.core.textures.TextureID",methodName="getData",strictMatch=true)
    public static class Read {
        @Patch.OnExit public static void exit(@Patch.This TextureID texture,
                @Patch.Return WrappedBuffer result) { HalfRuntime.expandReadback(texture,result); }
    }
    @Patch(className="zombie.core.textures.TextureID",methodName="setData",strictMatch=true)
    public static class Write {
        @Patch.OnEnter(skipOn=true) public static boolean enter(@Patch.This TextureID texture,
                @Patch.Argument(0) ByteBuffer pixels) { return HalfRuntime.promoteWrite(texture,pixels); }
    }
    @Patch(className="viewpoint.platform.GameTextures",methodName="follow",strictMatch=true)
    public static class Checkbox {
        @Patch.OnEnter(skipOn=true) public static boolean enter() { return HalfRuntime.supported(); }
        @Patch.OnExit public static void exit(@Patch.Return(readOnly=false) boolean result) {
            if (HalfRuntime.supported()) result=HalfRuntime.follow();
        }
    }
    @Patch(className="viewpoint.platform.LiveSettings",methodName="load",strictMatch=true)
    public static class SettingsLoad {
        // Covers both overloads without assuming arguments or a return type.
        @Patch.OnExit public static void exit(@Patch.AllArguments Object[] ignored) { HalfRuntime.restoreCheckbox(); }
    }
    @Patch(className="viewpoint.platform.LiveSettings",methodName="save",strictMatch=true)
    public static class SettingsSave {
        @Patch.OnEnter public static void enter() { HalfRuntime.follow(); }
    }

}

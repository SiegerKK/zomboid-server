import java.io.*;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.*;
import java.nio.*;
import java.nio.file.*;
import java.util.*;
import zombie.ZomboidFileSystem;
import zombie.core.textures.*;
import zombie.core.utils.*;
import siegerviewpointhalf.HalfRuntime;
import org.lwjgl.glfw.GLFW;
import org.lwjgl.opengl.*;

/** OPTIONAL local ABI/payload acceptance against real owner-installed jars; no stubs. */
public class ViewpointHalfEngineCheck {
    public static void premain(String args, Instrumentation inst) throws Exception {
        Class<?> loader=Class.forName("me.zed_0xff.zombie_buddy.Loader");
        Field f=loader.getDeclaredField("g_instrumentation");f.setAccessible(true);f.set(null,inst);
        me.zed_0xff.zombie_buddy.PatchEngine.applyPatches("siegerviewpointhalf",ViewpointHalfEngineCheck.class.getClassLoader());
        int n=me.zed_0xff.zombie_buddy.PatchEngine.collectPatches("siegerviewpointhalf",ViewpointHalfEngineCheck.class.getClassLoader()).size();
        if(n!=5)throw new AssertionError("Expected all 5 real ZombieBuddy patches; got "+n);
        for(String name:new String[]{"zombie.asset.FileTask_LoadPackImage","zombie.core.textures.TextureID","viewpoint.platform.GameTextures"})
            Class.forName(name,false,ViewpointHalfEngineCheck.class.getClassLoader());
        System.out.println("CHECK: real ZombieBuddy patch discovery and target transformations invoked");
    }
    static void check(boolean b,String message){if(!b)throw new AssertionError(message);}
    static Field field(Class<?> c,String key)throws Exception{Field f=c.getDeclaredField(key);f.setAccessible(true);return f;}
    static Object empty(Class<?> type)throws Exception{
        Field f=sun.misc.Unsafe.class.getDeclaredField("theUnsafe");f.setAccessible(true);
        return ((sun.misc.Unsafe)f.get(null)).allocateInstance(type);
    }
    public static void main(String[] args)throws Exception{
        // Isolated JVM cache; never touches the running game's configuration.
        Path cache=Path.of(args[0]);Files.createDirectories(cache);
        ZomboidFileSystem.instance.setCacheDir(cache.toString());
        ZomboidFileSystem.instance.init();
        if(Boolean.getBoolean("half.check.negative")) {
            check(!HalfRuntime.supported(),"Mismatched asset hash must disable adapter");
            check(zombie.core.Core.getInstance().getOptionTexture2x(),"Legacy getter untouched on rejection");
            System.out.println("PASS negative engine gate: mismatched assets rejected without legacy 1x");return;
        }
        check(HalfRuntime.supported(),"Exact real game/Viewpoint/assets hash gate must pass");
        if(Boolean.getBoolean("half.check.full")) {
            zombie.fileSystem.FileSystemImpl fs=new zombie.fileSystem.FileSystemImpl();
            fs.mountTexturePack("Tiles2x",new zombie.fileSystem.FileSystem.TexturePackTextures(),64);
            ImageData full=(ImageData)new zombie.asset.FileTask_LoadPackImage("Tiles2x","Tiles2x2",fs,null).call();
            check(full.getMipMapData(0).width==full.getWidthHW(),"Persisted Full uses original physical width");
            check(HalfRuntime.status().contains("active=false"),"Full active after separate JVM launch");
            Class<?> c=Class.forName("viewpoint.platform.GameTextures");
            Method follow=c.getDeclaredMethod("follow");follow.setAccessible(true);follow.invoke(null);
            Object toggle=field(c,"HALF").get(null);
            check(!(Boolean)toggle.getClass().getMethod("get").invoke(toggle),"Full checkbox restored after launch");
            full.dispose();System.out.println("PASS full engine restart: original payload and Full checkbox restored");return;
        }
        Properties props=new Properties();
        try(InputStream in=Files.newInputStream(Path.of(args[1]))){props.load(in);}
        String key=args[2],spec=props.getProperty("page."+key);
        check(spec!=null,"Page exists");
        String[] part=spec.split(",");int w=Integer.parseInt(part[1]),h=Integer.parseInt(part[2]);
        ImageData image;
        try(InputStream in=Files.newInputStream(Path.of(args[3]))){image=new ImageData(in,true);}
        image.initMipMaps();
        check(image.getWidth()==w&&image.getHeight()==h,"Original PNG dimensions");
        int hw=image.getWidthHW(),hh=image.getHeightHW();
        Object mask=image.mask;check(mask!=null,"Original full-resolution picking mask");
        Object task=empty(zombie.asset.FileTask_LoadPackImage.class);
        field(task.getClass(),"packName").set(task,key.substring(0,key.indexOf('/')));
        field(task.getClass(),"imageName").set(task,key.substring(key.indexOf('/')+1));
        field(task.getClass(),"flags").setInt(task,64);
        check(HalfRuntime.adapt(task,image)==image,"Payload adapted in place");
        check(image.getWidth()==w&&image.getHeight()==h,"Logical dimensions unchanged");
        check(image.getWidthHW()==hw&&image.getHeightHW()==hh,"Logical hardware dimensions unchanged");
        check(image.mask==mask,"Original picking mask preserved");
        check(image.getMipMapData(0).width==hw/2&&image.getMipMapData(0).height==hh/2,"Physical GPU mip level 0 halved");
        int mipCount=image.getMipMapCount();
        for(int i=0;i<mipCount;i++){
            MipMapLevel m=image.getMipMapData(i);
            check(m.width==Math.max(1,(hw/2)>>i)&&m.height==Math.max(1,(hh/2)>>i),"Valid mip dimensions "+i);
            check(m.getBuffer().remaining()>=m.width*m.height*4,"Mip buffer sufficient "+i);
        }
        // All patched readback math runs on real engine WrappedBuffer objects.
        Constructor<TextureID> constructor=TextureID.class.getDeclaredConstructor();constructor.setAccessible(true);
        TextureID texture=constructor.newInstance();HalfRuntime.remember(texture,image);
        WrappedBuffer buf=DirectBufferAllocator.allocate(hw*hh*4);
        ByteBuffer b=buf.getBuffer();
        for(int i=0;i<(hw/2)*(hh/2);i++) b.putInt(i*4,i);
        HalfRuntime.expandReadback(texture,buf);
        for(int y=0;y<hh;y++)for(int x=0;x<hw;x++)
            check(b.getInt((y*hw+x)*4)==(y/2)*(hw/2)+x/2,"Logical readback stride");
        buf.dispose();
        // The patched checkbox must leave Core.tileScale and the disabled legacy getter alone.
        Class<?> c=Class.forName("viewpoint.platform.GameTextures");
        Method follow=c.getDeclaredMethod("follow");follow.setAccessible(true);
        follow.invoke(null);
        Object toggle=field(c,"HALF").get(null);
        check((Boolean)toggle.getClass().getMethod("get").invoke(toggle),"Checkbox initially Half");
        toggle.getClass().getMethod("set",boolean.class).invoke(toggle,false);follow.invoke(null);
        check(Files.readString(cache.resolve("sieger-viewpoint-half.properties")).contains("enabled=false"),"Full selection persisted");
        toggle.getClass().getMethod("set",boolean.class).invoke(toggle,true);follow.invoke(null);
        check(Files.readString(cache.resolve("sieger-viewpoint-half.properties")).contains("enabled=true"),"Half selection persisted");
        check(zombie.core.Core.getInstance().getOptionTexture2x(),"Legacy getter untouched");
        // Exercise the genuine patched pack file worker, not only a direct helper call.
        zombie.fileSystem.FileSystemImpl fs=new zombie.fileSystem.FileSystemImpl();
        zombie.fileSystem.FileSystem.TexturePackTextures lookup=new zombie.fileSystem.FileSystem.TexturePackTextures();
        fs.mountTexturePack("Tiles2x",lookup,64);
        ImageData fromTask=(ImageData)new zombie.asset.FileTask_LoadPackImage("Tiles2x","Tiles2x2",fs,null).call();
        check(fromTask.getWidth()==w && fromTask.getMipMapData(0).width==hw/2,"Real patched file worker payload");
        fromTask.dispose();
        if(Boolean.getBoolean("half.check.gl")) glCheck(texture,image,hw,hh);
        // A corrupt sidecar must retain the ORIGINAL ready-to-upload full pixel payload.
        Properties live=(Properties)field(HalfRuntime.class,"manifest").get(null);
        live.setProperty("page."+key,part[0]+","+part[1]+","+part[2]+","+"0".repeat(64));
        ImageData fallback;
        try(InputStream in=Files.newInputStream(Path.of(args[3]))){fallback=new ImageData(in,true);}
        MipMapLevel before=fallback.data;
        check(HalfRuntime.adapt(task,fallback)==fallback && fallback.data==before,"Corrupt asset retains original pixel ownership");
        check(fallback.getMipMapData(0).width==hw,"Corrupt asset uses Full dimensions");fallback.dispose();
        System.out.println("PASS actual engine pixels/mips, logical geometry, masks, readback, checkbox restart configuration and corrupt-PNG fallback: "+HalfRuntime.status());
        image.dispose();
    }
    static void glCheck(TextureID texture,ImageData image,int hw,int hh)throws Exception{
        check(GLFW.glfwInit(),"GLFW initialization");
        GLFW.glfwWindowHint(GLFW.GLFW_VISIBLE,GLFW.GLFW_FALSE);
        long window=GLFW.glfwCreateWindow(64,64,"Sieger half isolated acceptance",0,0);
        check(window!=0,"Hidden independent GL context");
        try {
            GLFW.glfwMakeContextCurrent(window);
            GLCapabilities caps=GL.createCapabilities();
            field(org.lwjglx.opengl.Display.class,"capabilities").set(null,caps);
            field(TextureID.class,"data").set(texture,image);
            field(TextureID.class,"id").setInt(texture,-1);
            TextureID.TextureIDAssetParams params=new TextureID.TextureIDAssetParams();
            field(params.getClass(),"flags").setInt(params,64);
            texture.assetParams=params;
            Method upload=TextureID.class.getDeclaredMethod("createTexture",boolean.class);upload.setAccessible(true);
            upload.invoke(texture,true); // real vanilla upload, full logical dimensions, half physical mip levels
            check(GL11.glGetTexLevelParameteri(GL11.GL_TEXTURE_2D,0,GL11.GL_TEXTURE_WIDTH)==hw/2,"Actual GL half-width allocation");
            check(GL11.glGetTexLevelParameteri(GL11.GL_TEXTURE_2D,0,GL11.GL_TEXTURE_HEIGHT)==hh/2,"Actual GL half-height allocation");
            check(GL11.glGetError()==0,"No GL errors after real upload");
            WrappedBuffer data=texture.getData(); // real patched glGetTexImage + logical-stride adapter
            check(data.getBuffer().capacity()>=hw*hh*4,"Actual readback retains logical capacity");
            check(GL11.glGetError()==0,"No GL errors on readback");
            texture.setData(data.getBuffer()); // real patched mutable-page promotion
            check(GL11.glGetTexLevelParameteri(GL11.GL_TEXTURE_2D,0,GL11.GL_TEXTURE_WIDTH)==hw,"Mutable page promoted to Full");
            check(GL11.glGetError()==0,"No GL errors on promotion");
            data.dispose();
            GL11.glDeleteTextures(field(TextureID.class,"id").getInt(texture));
            System.out.println("PASS GPU: real vanilla texture upload HALF, patched readback, mutable FULL promotion; renderer="+GL11.glGetString(GL11.GL_RENDERER));
        } finally {GLFW.glfwDestroyWindow(window);GLFW.glfwTerminate();}
    }
}

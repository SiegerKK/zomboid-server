package siegerviewpointhalf;

import java.io.*;
import java.lang.reflect.*;
import java.nio.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import zombie.ZomboidFileSystem;
import zombie.core.textures.*;
import zombie.core.utils.WrappedBuffer;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GL30;

/** Independent pixel-payload adapter. Does not switch Core.tileScale or pack lookup. */
public final class HalfRuntime {
    private static boolean initialized, supported, desired = true;
    private static Boolean active;
    private static Path assets, config;
    private static Properties manifest;
    private static String gamePin, viewPin;
    private static final Map<ImageData, int[]> images = Collections.synchronizedMap(new WeakHashMap<>());
    private static final Map<TextureID, int[]> textures = Collections.synchronizedMap(new WeakHashMap<>());
    private static final Set<String> failed = Collections.synchronizedSet(new HashSet<>());
    private static final AtomicLong adapted = new AtomicLong();
    private static final AtomicLong savedBaseBytes = new AtomicLong();
    private static final AtomicLong readbacks = new AtomicLong();
    private static final AtomicLong promotions = new AtomicLong();
    private HalfRuntime() {}

    public static void log(String s) { System.out.println("[SiegerViewpointHalf] " + s); }
    private static Field field(Class<?> c, String name) throws ReflectiveOperationException {
        Field f = c.getDeclaredField(name); f.setAccessible(true); return f;
    }
    private static Object get(Object o, String key) throws ReflectiveOperationException {
        return field(o.getClass(), key).get(o);
    }
    private static String hash(Path p) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (InputStream in = Files.newInputStream(p)) {
            byte[] b = new byte[1048576]; int n;
            while ((n=in.read(b)) != -1) md.update(b,0,n);
        }
        return HexFormat.of().formatHex(md.digest());
    }
    private static Path origin(Class<?> c) throws Exception {
        return Path.of(c.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
    }
    private static Properties properties(Path p) throws IOException {
        Properties v = new Properties();
        try (InputStream in = Files.newInputStream(p)) { v.load(in); }
        return v;
    }
    public static synchronized boolean supported() {
        if (initialized) return supported;
        if (!ZomboidFileSystem.instance.isInitialized()) return false;
        initialized = true;
        try {
            // The build pins are embedded, not trusted from a user-editable asset manifest.
            Properties pins = new Properties();
            try (InputStream in = HalfRuntime.class.getResourceAsStream("/half-build.properties")) {
                if (in == null) throw new IOException("Missing build pins"); pins.load(in);
            }
            gamePin=pins.getProperty("game.sha256"); viewPin=pins.getProperty("viewpoint.sha256");
            Class<?> view = Class.forName("viewpoint.platform.GameTextures", false, HalfRuntime.class.getClassLoader());
            if (!gamePin.equals(hash(origin(zombie.core.Core.class))) || !viewPin.equals(hash(origin(view))))
                throw new IOException("Game/Viewpoint SHA-256 changed; rebuild and review required");
            Path jar = origin(HalfRuntime.class);
            assets=jar.getParent().getParent().getParent().resolve("half-atlases").toRealPath();
            manifest=properties(assets.resolve("assets.properties"));
            if (!gamePin.equals(manifest.getProperty("game.sha256")) || !viewPin.equals(manifest.getProperty("viewpoint.sha256")))
                throw new IOException("Assets belong to a different build");
            Path game=origin(zombie.core.Core.class).getParent();
            for (String key:manifest.stringPropertyNames()) {
                if (!key.startsWith("pack.") || !key.endsWith(".sha256")) continue;
                String pack=key.substring(5,key.length()-7);
                Path original=game.resolve("media/texturepacks/"+pack+".pack").toRealPath();
                Path mounted=Path.of(ZomboidFileSystem.instance.getString("media/texturepacks/"+pack+".pack")).toRealPath();
                if (!original.equals(mounted) || !manifest.getProperty(key).equals(hash(original)))
                    throw new IOException("Pack modified or overridden: "+pack);
            }
            config=Path.of(ZomboidFileSystem.instance.getCacheDir()).resolve("sieger-viewpoint-half.properties");
            if (Files.exists(config)) desired=Boolean.parseBoolean(properties(config).getProperty("enabled","true"));
            else {
                Path legacy=config.resolveSibling("viewpoint-live.properties");
                if (Files.exists(legacy)) desired=Boolean.parseBoolean(properties(legacy).getProperty("graphics.halfTextures","false"));
            }
            // Preflight reflective ABI before touching any payload.
            for (String f:new String[]{"mipMaps","mipMapCount","preMultipliedAlphaDone"}) field(ImageData.class,f);
            field(zombie.asset.FileTask_LoadPackImage.class,"packName");
            field(zombie.asset.FileTask_LoadPackImage.class,"imageName");
            field(zombie.asset.FileTask_LoadPackImage.class,"flags");
            supported=true;
            restoreCheckbox();
            log("ready; selected="+(desired?"HALF":"FULL")+"; logical scale remains 2x; restart required for changes");
        } catch (Exception | LinkageError e) {
            log("DISABLED; normal Full loader retained: "+e);
        }
        return supported;
    }
    private static synchronized boolean active() {
        if (!supported()) return false;
        if (!uiInitialized) restoreCheckbox();
        if (active==null) { active=desired; log("session="+(active?"HALF":"FULL")); }
        return active;
    }
    private static Object toggle() throws ReflectiveOperationException {
        Class<?> c=Class.forName("viewpoint.platform.GameTextures");
        return field(c,"HALF").get(null);
    }
    // Called after real LiveSettings.load as well as the first texture worker.
    // The game need not visit Graphics.changed()/GameTextures.follow at startup.
    public static synchronized void restoreCheckbox() {
        if (!supported()) return;
        try {
            Class<?> settings=Class.forName("viewpoint.platform.LiveSettings");
            if (!field(settings,"loaded").getBoolean(null)) return;
            Object value=toggle();
            if(value==null) return; // class initialization in progress; retry on first payload
            value.getClass().getMethod("set",boolean.class).invoke(value,desired);
            value.getClass().getMethod("describe",String.class).invoke(value,
                "Sieger half-resolution CURRENT 2x atlas payloads. Logical sprite size unchanged. " +
                "FULL CLIENT RESTART required. Current session: "+(Boolean.TRUE.equals(active)?"Half":active==null?"not loaded":"Full"));
            uiInitialized=true;
        } catch (ReflectiveOperationException e) { log("UI restore failed: "+e); }
    }
    public static synchronized boolean follow() {
        if (!supported()) return false;
        try {
            Object value=toggle();
            if(value==null) return false;
            boolean selected=(Boolean)value.getClass().getMethod("get").invoke(value);
            if(selected!=desired) {
                save(selected); desired=selected;
                log("next launch="+(desired?"HALF":"FULL")+"; current textures unchanged");
            }
        } catch (ReflectiveOperationException | IOException e) { log("UI update failed: "+e); }
        return false;
    }
    private static boolean uiInitialized;
    private static void save(boolean value) throws IOException {
        Path tmp=Files.createTempFile(config.getParent(),".sieger-half-",".tmp");
        try {
            Files.writeString(tmp,"enabled="+value+"\n");
            Files.move(tmp,config,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        } finally { Files.deleteIfExists(tmp); }
    }
    public static Object adapt(Object task,Object result) {
        if (!(result instanceof ImageData original) || !active()) return result;
        String key="unknown";
        ImageData small=null;
        try {
            String pack=(String)get(task,"packName"),page=(String)get(task,"imageName");
            key=pack+"/"+page;
            String value=manifest.getProperty("page."+key);
            if (value==null || failed.contains(key)) return result;
            int flags=(Integer)get(task,"flags");
            if ((flags & 64)==0 || (flags & (16|128|256|512))!=0) throw new IOException("Unsupported pack flags");
            String[] parts=value.split(",");
            if (parts.length!=4 || !parts[0].matches("[0-9a-f]{64}\\.png")) throw new IOException("Invalid page descriptor");
            int w=Integer.parseInt(parts[1]),h=Integer.parseInt(parts[2]);
            if (w!=original.getWidth() || h!=original.getHeight()) throw new IOException("Original page dimensions changed");
            Path p=assets.resolve(parts[0]);
            if (Files.isSymbolicLink(p) || !p.toRealPath().getParent().equals(assets) || !hash(p).equals(parts[3]))
                throw new IOException("Invalid half PNG SHA-256/path");
            try (InputStream in=Files.newInputStream(p)) { small=new ImageData(in,false); }
            int pw=original.getWidthHW()/2,ph=original.getHeightHW()/2;
            if (small.getWidth()!=pw || small.getHeight()!=ph) throw new IOException("Half page dimensions changed");
            small.initMipMaps();
            // Transfer only pixel levels. Original logical dimensions AND full-resolution
            // alpha picking mask remain intact; the vanilla uploader uses mip dimensions.
            Field mip=field(ImageData.class,"mipMaps"),count=field(ImageData.class,"mipMapCount");
            Object chain=mip.get(small); int n=small.getMipMapCount();
            original.dispose();
            original.data=small.data; mip.set(original,chain); count.setInt(original,n);
            field(ImageData.class,"preMultipliedAlphaDone").setBoolean(original,true);
            original.alphaPaddingDone=true;
            small.data=null; mip.set(small,null);
            images.put(original,new int[]{original.getWidthHW(),original.getHeightHW(),pw,ph});
            long pages=adapted.incrementAndGet();
            savedBaseBytes.addAndGet((long)pw*ph*12);
            if (pages==1 || pages%64==0) log("pages="+pages+" uploaded_baseRGBA_reduction_MiB="+savedBaseBytes.get()/1048576);
            return result;
        } catch (Exception | LinkageError e) {
            if (failed.add(key)) log("FULL fallback page="+key+" reason="+e);
            return result;
        } finally { if (small!=null) small.dispose(); }
    }
    public static void remember(TextureID id,ImageData data) {
        int[] dims=images.remove(data);
        if (dims!=null) textures.put(id,dims); else textures.remove(id);
    }
    public static void expandReadback(TextureID id,WrappedBuffer wrapped) {
        int[] d=textures.get(id);
        if (d==null || wrapped==null) return;
        ByteBuffer b=wrapped.getBuffer();
        if (b.capacity()<(long)d[0]*d[1]*4) throw new IllegalStateException("Logical readback buffer too small");
        // GL wrote compact physical rows. Expand backwards in the existing logical
        // buffer to keep vanilla getData()/mask consumers' full-resolution stride.
        for (int y=d[1]-1;y>=0;y--) for (int x=d[0]-1;x>=0;x--) {
            int from=((y/2)*d[2]+x/2)*4,to=(y*d[0]+x)*4;
            int rgba=b.getInt(from); b.putInt(to,rgba);
        }
        readbacks.incrementAndGet();
    }
    public static boolean promoteWrite(TextureID id,ByteBuffer pixels) {
        int[] d=textures.get(id);
        if (d==null || pixels==null) return false;
        if (pixels.remaining()<(long)d[0]*d[1]*4) throw new IllegalArgumentException("Logical write buffer too small");
        // An addon writes this formerly static page: safely promote it to FULL.
        // Never let vanilla glTexSubImage2D write logical dimensions into a half allocation.
        id.bind();
        GL11.glTexImage2D(GL11.GL_TEXTURE_2D,0,GL11.GL_RGBA8,d[0],d[1],0,GL11.GL_RGBA,GL11.GL_UNSIGNED_BYTE,pixels);
        GL30.glGenerateMipmap(GL11.GL_TEXTURE_2D);
        textures.remove(id); promotions.incrementAndGet();
        log("mutable page promoted to FULL; promotions="+promotions.get());
        return true;
    }
    public static String status() {
        return "supported="+supported()+" active="+active+" selected="+desired+" pages="+adapted.get()+
            " uploaded_baseRGBA_reduction_MiB="+savedBaseBytes.get()/1048576+" fallback_pages="+failed.size()+
            " readbacks="+readbacks.get()+" promotions="+promotions.get();
    }
}

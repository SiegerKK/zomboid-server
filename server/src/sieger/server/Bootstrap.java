package sieger.server;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.UUID;

/** Uses the existing ZombieBuddy lifecycle callback. No transformers or game patches. */
public final class Bootstrap implements Runnable {
    private static String world;
    private static boolean registered,started;
    public static synchronized void premain(String selectedWorld,Instrumentation unused){
      try{
        if(registered)return;
        if(selectedWorld==null||!selectedWorld.matches("[A-Za-z0-9][A-Za-z0-9_-]{0,39}"))
            throw new IllegalArgumentException("Explicit world required");
        world=selectedWorld;
        Object callback=Class.forName("me.zed_0xff.zombie_buddy.Callbacks").getField("onGameInitComplete").get(null);
        callback.getClass().getMethod("register",Runnable.class).invoke(callback,new Bootstrap());
        registered=true;
      }catch(Throwable error){System.err.println("SIEGER_SERVER bootstrap registration disabled: "+error.getClass().getSimpleName());}
    }
    public void run(){
        if(started)return;started=true;
        try{
            Class<?> server=Class.forName("zombie.network.GameServer");
            Class<?> lua=Class.forName("zombie.Lua.LuaManager");
            if(!server.getField("server").getBoolean(null)||
               server.getField("mainThread").get(null)!=Thread.currentThread()||
               !lua.getField("checksumDone").getBoolean(null))throw new IllegalStateException("Server lifecycle not ready");
            Object core=Class.forName("zombie.core.Core").getMethod("getInstance").invoke(null);
            String version=core.getClass().getMethod("getVersion").invoke(core).toString();
            if(!version.equals("42.21")&&!version.startsWith("42.21."))throw new IllegalStateException("Unreviewed game version");
            Path dir=Paths.get(System.getProperty("sieger.server.data","/root/Zomboid/Lua"));Files.createDirectories(dir);
            for(String name:new String[]{"SiegerServerReady.txt","SiegerServerAnimalsRequest.txt","SiegerServerAnimalsResult.txt","SiegerServerAnimalsGuard.txt"}){
                Path p=dir.resolve(name);
                if(Files.isSymbolicLink(p))throw new IllegalStateException("Symlink control file");
                if(!Files.exists(p))Files.createFile(p,PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
                Files.setPosixFilePermissions(p,PosixFilePermissions.fromString("rw-------"));
            }
            Object env=lua.getField("env").get(null),platform=lua.getField("platform").get(null);
            Object data=platform.getClass().getMethod("newTable").invoke(platform);
            Class<?> table=Class.forName("se.krka.kahlua.vm.KahluaTable");
            Method put=table.getMethod("rawset",Object.class,Object.class);
            put.invoke(data,"world",world);put.invoke(data,"boot",UUID.randomUUID().toString());
            put.invoke(data,"revision","animals-v1");put.invoke(data,"game_version",version);
            put.invoke(env,"SiegerServerBootstrap",data);
            lua.getMethod("RunLua",String.class).invoke(null,"/bootstrap/sieger-server/SiegerServer.lua");
            Object revision=table.getMethod("rawget",Object.class).invoke(env,"SiegerServerModuleRevision");
            if(!"animals-v1".equals(revision))throw new IllegalStateException("Server module did not initialize");
            System.out.println("SIEGER_SERVER bootstrap loaded world="+world);
        }catch(Throwable error){System.err.println("SIEGER_SERVER bootstrap disabled: "+error.getClass().getSimpleName());}
    }
}

package sieger.server;

import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.attribute.PosixFilePermissions;
import java.lang.reflect.*;
import java.util.*;

/** All game objects are read on the game's event thread. No game-state setters. */
public final class Animals {
    static String world;
    static final Path DIR=Path.of(System.getProperty("sieger.server.data","/root/Zomboid/Lua"));
    static final String BOOT=UUID.randomUUID().toString();
    static long nextPoll;
    static boolean ready,disabled;
    static String id;
    static List<?> source;
    static int cursor,errors,unloaded,within;
    static long started;
    static Double ax,ay,az;
    static int radius;
    static String player;
    static final List<String> rows=new ArrayList<>();
    static Object call(Object obj,String method)throws Exception{
        return obj.getClass().getMethod(method).invoke(obj);
    }
    static Object optional(Object obj,String method){try{return call(obj,method);}catch(Exception e){return null;}}
    static String quote(Object o){
        if(o==null)return "null";
        String s=o.toString();StringBuilder b=new StringBuilder("\"");
        for(int i=0;i<s.length();i++){char c=s.charAt(i);
            if(c=='"'||c=='\\')b.append('\\').append(c);
            else if(c<32)b.append(String.format("\\u%04x",(int)c));else b.append(c);}
        return b.append('"').toString();
    }
    static String scalar(Object v){
        if(v==null)return "null";
        if(v instanceof Number){double d=((Number)v).doubleValue();return Double.isFinite(d)?v.toString():"null";}
        if(v instanceof Boolean)return v.toString();return quote(v);
    }
    static void write(String name,String body)throws Exception{
        Path dest=DIR.resolve(name),tmp=DIR.resolve(name+".tmp");
        if(Files.isSymbolicLink(dest)||Files.isSymbolicLink(tmp))throw new IllegalStateException("Unsafe file");
        try(var channel=Files.newByteChannel(tmp,EnumSet.of(StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE),
                PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")))){
            java.nio.ByteBuffer bytes=StandardCharsets.UTF_8.encode(body+"\n");
            while(bytes.hasRemaining())channel.write(bytes);
        }
        Files.move(tmp,dest,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
    }
    static String header(String status){return "{\"schema\":1,\"world\":"+quote(world)+",\"boot\":"+quote(BOOT)+
        ",\"request_id\":"+quote(id)+",\"status\":"+quote(status);}
    static void tick()throws Exception{
        if(disabled)return;
        if(source==null && ready && System.currentTimeMillis()<nextPoll)return;
        if(Class.forName("zombie.network.GameServer").getField("mainThread").get(null)!=Thread.currentThread())return;
        if(!Class.forName("zombie.network.GameServer").getField("server").getBoolean(null) ||
           !Class.forName("zombie.Lua.LuaManager").getField("checksumDone").getBoolean(null))return;
        if(!ready){Files.createDirectories(DIR);write("SiegerServerReady.json",header("ready")+
            ",\"module\":\"animals-v1\",\"pid\":"+ProcessHandle.current().pid()+"}");ready=true;
            System.out.println("SIEGER_SERVER animals-v1 ready world="+world);}
        if(source!=null){step();return;}
        long now=System.currentTimeMillis();if(now<nextPoll)return;nextPoll=now+1000;
        Path req=DIR.resolve("SiegerServerAnimals.request");
        if(!Files.isRegularFile(req,LinkOption.NOFOLLOW_LINKS)||Files.size(req)>256)return;
        String[] f=Files.readString(req).strip().split("\\t",-1);
        if(f.length!=7||!f[0].equals("v1")||!f[1].matches("[0-9a-f]{32}")||
           !f[2].equals(world)||!f[3].matches("[A-Za-z0-9_][A-Za-z0-9_.-]{0,30}")||
           !f[4].matches("[0-9]{1,3}")||!f[5].matches("[0-9]{13}")||!f[6].equals(BOOT))return;
        Path guard=DIR.resolve("SiegerServerAnimals.guard");
        if(Files.isSymbolicLink(guard))return;
        if(Files.isRegularFile(guard)&&Files.readString(guard).strip().equals(f[1]))return;
        id=f[1];write("SiegerServerAnimals.guard",id);
        long expiry=Long.parseLong(f[5]);radius=Integer.parseInt(f[4]);
        if(now>expiry||expiry>now+60000||radius<1||radius>500)throw new IllegalArgumentException("Expired/radius");
        player=f[3];Object anchor=Class.forName("zombie.network.GameServer")
            .getMethod("getPlayerByUserName",String.class).invoke(null,player);
        if(anchor==null)throw new IllegalArgumentException("Player not connected");
        ax=((Number)call(anchor,"getX")).doubleValue();ay=((Number)call(anchor,"getY")).doubleValue();az=((Number)call(anchor,"getZ")).doubleValue();
        Object iso=Class.forName("zombie.iso.IsoWorld").getField("instance").get(null);
        Object cell=call(iso,"getCell");
        // Exact B42.21 getter copies IsoAnimals out of loaded objectList; no chunk generation.
        source=(List<?>)call(cell,"getAnimals");cursor=errors=unloaded=within=0;rows.clear();started=now;
        if(source.size()>10000)throw new IllegalStateException("Animal budget exceeded");
        write("SiegerServerAnimals.json",header("running")+"}");
        step();
    }
    static void step()throws Exception{
        long deadline=System.nanoTime()+2_000_000;int budget=128;
        while(cursor<source.size()&&budget-->0&&System.nanoTime()<deadline){
            Object a=source.get(cursor++);
            try{
                if(a==null||call(a,"getSquare")==null){unloaded++;continue;}
                double x=((Number)call(a,"getX")).doubleValue(),y=((Number)call(a,"getY")).doubleValue();
                double z=((Number)call(a,"getZ")).doubleValue(),d=Math.hypot(x-ax,y-ay);
                if(!Double.isFinite(d)||!Double.isFinite(z))throw new IllegalArgumentException("Invalid coordinates");
                if(d>radius)continue;within++;
                Object breed=optional(a,"getBreed");
                rows.add("{\"animal_id\":"+scalar(optional(a,"getAnimalID"))+
                    ",\"type\":"+scalar(optional(a,"getAnimalType"))+",\"breed\":"+scalar(breed==null?null:optional(breed,"getName"))+
                    ",\"x\":"+x+",\"y\":"+y+",\"z\":"+z+",\"distance_tiles_2d\":"+d+
                    ",\"health\":"+scalar(optional(a,"getHealth"))+",\"dead\":"+scalar(optional(a,"isDead"))+
                    ",\"age\":"+scalar(optional(a,"getAge"))+",\"baby\":"+scalar(optional(a,"isBaby"))+"}");
            }catch(Exception e){errors++;}
        }
        if(cursor<source.size())return;
        write("SiegerServerAnimals.json",header(errors==0?"complete":"partial")+
            ",\"player\":"+quote(player)+",\"anchor\":{\"x\":"+ax+",\"y\":"+ay+",\"z\":"+az+"}"+
            ",\"radius\":"+radius+",\"inspected\":"+cursor+",\"unloaded\":"+unloaded+",\"errors\":"+errors+
            ",\"count\":"+within+",\"elapsed_ms\":"+(System.currentTimeMillis()-started)+
            ",\"scope\":\"loaded IsoAnimal objects only; no virtual populations or hutch inventory\",\"animals\":["+String.join(",",rows)+"]}");
        source=null;rows.clear();
    }
    static void fail(Throwable e){
        if(!ready)disabled=true;
        source=null;rows.clear();
        System.err.println("SIEGER_SERVER animals failure: "+e.getClass().getSimpleName());
        try{if(ready&&id!=null)write("SiegerServerAnimals.json",header("error")+",\"reason\":\"review_server_logs\"}");}catch(Exception ignored){}
    }
}

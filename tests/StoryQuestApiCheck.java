/** Metadata-only contract check against pinned game classes. Does NOT spawn. */
public class StoryQuestApiCheck {
  public static void main(String[] args) throws Exception {
    ClassLoader loader=StoryQuestApiCheck.class.getClassLoader();
    Class<?> api=Class.forName("zombie.Lua.LuaManager$GlobalObject",false,loader);
    var spawn=api.getMethod("addZombiesInOutfit",int.class,int.class,int.class,int.class,String.class,Integer.class);
    if (!java.util.List.class.isAssignableFrom(spawn.getReturnType())) throw new AssertionError("Spawn does not return a list");
    Class<?> zombie=Class.forName("zombie.characters.IsoZombie",false,loader);
    for (String method:new String[]{"getModData","getOnlineID","getX","getY","getZ"}) zombie.getMethod(method);
    System.out.println("PASS: pinned B42 spawn/modData API metadata; real map spawn/client sync NOT tested");
  }
}

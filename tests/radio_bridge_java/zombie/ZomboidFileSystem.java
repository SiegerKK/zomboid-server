package zombie;
public final class ZomboidFileSystem {
    public static final ZomboidFileSystem instance = new ZomboidFileSystem();
    public String getModDir(String id) {
        return "SiegerRadio".equals(id) ? System.getProperty("radio.test.mod") : null;
    }
}

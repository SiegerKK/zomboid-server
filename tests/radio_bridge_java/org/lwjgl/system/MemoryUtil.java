package org.lwjgl.system;
import java.nio.ByteBuffer;
/** Test-only owned pointer slot; never part of the shipped bridge JAR. */
public class MemoryUtil {
 private static ByteBuffer slot;
 public static long memAddress(ByteBuffer buffer) {slot=buffer;return 1024L;}
 public static ByteBuffer buffer(long address) {
  if(address!=1024L)throw new AssertionError("Only owned pointer slot");return slot;
 }
}

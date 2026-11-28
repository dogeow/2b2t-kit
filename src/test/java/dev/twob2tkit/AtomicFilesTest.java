package dev.twob2tkit;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class AtomicFilesTest {
    @TempDir Path directory;

    @Test void replacesTheConfigWholeAndLeavesNoTemporaryFile() throws IOException {
        Path target = directory.resolve("twob2tkit.json");
        Files.writeString(target, "{\"old\":true}");
        AtomicFiles.write(target, writer -> writer.write("{\"new\":true}"));
        assertEquals("{\"new\":true}", Files.readString(target));
        assertFalse(Files.exists(directory.resolve("twob2tkit.json.tmp")));
    }

    @Test void aFailedWriteKeepsThePreviousConfigIntact() throws IOException {
        Path target = directory.resolve("twob2tkit.json");
        Files.writeString(target, "{\"areas\":[1,2,3]}");
        assertThrows(IOException.class, () -> AtomicFiles.write(target, writer -> {
            writer.write("{\"areas\":[");
            throw new IOException("simulated crash mid-write");
        }));
        assertEquals("{\"areas\":[1,2,3]}", Files.readString(target));
        assertFalse(Files.exists(directory.resolve("twob2tkit.json.tmp")));
    }

    @Test void createsTheConfigDirectoryOnFirstSave() throws IOException {
        Path target = directory.resolve("config/twob2tkit.json");
        AtomicFiles.write(target, writer -> writer.write("{}"));
        assertEquals("{}", Files.readString(target));
    }
    @Test void anUnreadableConfigIsCopiedAsideBeforeDefaultsCanOverwriteIt() throws IOException {
        Path target = directory.resolve("twob2tkit.json");
        Files.writeString(target, "{\"areas\":[1,2");
        Path kept = AtomicFiles.keepAside(target, "123");
        assertEquals(directory.resolve("twob2tkit.json.unreadable-123"), kept);
        assertEquals("{\"areas\":[1,2", Files.readString(kept));
        AtomicFiles.write(target, writer -> writer.write("{}"));
        assertEquals("{\"areas\":[1,2", Files.readString(kept), "the copy survives the next save");
        assertNull(AtomicFiles.keepAside(directory.resolve("missing.json"), "1"));
        Files.writeString(directory.resolve("empty.json"), "");
        assertNull(AtomicFiles.keepAside(directory.resolve("empty.json"), "1"), "nothing worth keeping");
    }
}

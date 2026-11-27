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
}

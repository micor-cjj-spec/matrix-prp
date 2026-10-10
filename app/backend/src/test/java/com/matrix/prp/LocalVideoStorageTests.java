package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.matrix.prp.video.LocalVideoStorage;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LocalVideoStorageTests {
    @TempDir Path root;

    @Test
    void assembledFilesUsePerUserOpaqueKeysAndNeverExposeInputName() throws Exception {
        LocalVideoStorage storage = new LocalVideoStorage(root.toString());
        String upload = UUID.randomUUID().toString();
        String key = UUID.randomUUID().toString();
        byte[] first = {0,0,0,20,'f','t','y','p'};
        byte[] second = {'i','s','o','m'};
        storage.writePart(13L, upload, 0, first);
        storage.writePart(13L, upload, 1, second);
        assertThat(storage.hasPart(13, upload, 0, first.length)).isTrue();
        assertThat(storage.hasPart(13, upload, 1, 999)).isFalse();
        assertThat(storage.firstPartHeader(13, upload)).isEqualTo(first);
        storage.complete(13, upload, key, 2, 12);
        assertThat(storage.mediaExists(13, key)).isTrue();
        assertThat(storage.mediaExists(14, key)).isFalse();
        assertThat(storage.mediaSize(13, key)).isEqualTo(12);
        assertThat(storage.internalRedirect(13, key))
                .isEqualTo("/_internal_prp_video/13/" + key + ".mp4");
        try (var channel = storage.readMedia(13, key)) {
            channel.position(4);
            ByteBuffer buffer = ByteBuffer.allocate(4);
            assertThat(channel.read(buffer)).isEqualTo(4);
            assertThat(buffer.array()).isEqualTo(new byte[]{'f','t','y','p'});
        }
        storage.removeUpload(13, upload);
        assertThat(Files.exists(root.resolve("temp/13").resolve(upload))).isFalse();
        storage.removeMedia(13, key);
        assertThat(storage.mediaExists(13, key)).isFalse();
    }

    @Test
    void rejectsPathEscapeAndInvalidUsers() throws Exception {
        LocalVideoStorage storage = new LocalVideoStorage(root.toString());
        assertThatThrownBy(() -> storage.mediaExists(1, "../etc/passwd"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> storage.removeUpload(0, UUID.randomUUID().toString()))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

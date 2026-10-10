package com.matrix.prp.video;

import java.io.IOException;
import java.nio.channels.SeekableByteChannel;

/**
 * Storage boundary: the domain service never constructs filesystem paths.
 * An S3 implementation can replace this adapter without changing video metadata APIs.
 */
public interface VideoStorage {
    void writePart(long userId, String uploadId, int partNo, byte[] bytes) throws IOException;
    boolean hasPart(long userId, String uploadId, int partNo, long expectedLength) throws IOException;
    byte[] firstPartHeader(long userId, String uploadId) throws IOException;
    void complete(long userId, String uploadId, String key, int parts, long size) throws IOException;
    void removeUpload(long userId, String uploadId) throws IOException;
    void removeMedia(long userId, String key) throws IOException;
    boolean mediaExists(long userId, String key);
    long mediaSize(long userId, String key) throws IOException;
    SeekableByteChannel readMedia(long userId, String key) throws IOException;

    /**
     * Optional internal Nginx path. The external /api/video/media endpoint must
     * authenticate the signed ticket BEFORE sending X-Accel-Redirect.
     */
    String internalRedirect(long userId, String key);
}

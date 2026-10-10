package com.matrix.prp.video;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.video.VideoDtos.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("!test")
@RequestMapping("/api/video")
public class VideoController {
    private final VideoLibraryService library;
    private final VideoStorage storage;
    private final boolean nginxDelivery;

    public VideoController(VideoLibraryService library, VideoStorage storage,
            @Value("${matrix-prp.video.delivery:java}") String delivery) {
        this.library = library;
        this.storage = storage;
        if (!"java".equalsIgnoreCase(delivery) && !"nginx".equalsIgnoreCase(delivery)) {
            throw new IllegalArgumentException("matrix-prp.video.delivery must be java or nginx");
        }
        this.nginxDelivery = "nginx".equalsIgnoreCase(delivery);
    }

    @GetMapping("/folders")
    public ApiResponse<List<Folder>> folders() {
        return ApiResponse.success(library.folders());
    }

    @PostMapping("/folders")
    public ApiResponse<Folder> createFolder(@Valid @RequestBody FolderRequest request) {
        return ApiResponse.success(library.createFolder(request));
    }

    @PutMapping("/folders/{id}")
    public ApiResponse<Folder> renameFolder(@PathVariable long id, @RequestBody FolderRequest request) {
        return ApiResponse.success(library.renameFolder(id, request.name()));
    }

    @DeleteMapping("/folders/{id}")
    public ApiResponse<Void> deleteFolder(@PathVariable long id) {
        library.deleteFolder(id);
        return ApiResponse.success();
    }

    @GetMapping("/items")
    public ApiResponse<List<Video>> videos(@RequestParam(required = false) Long folderId) {
        return ApiResponse.success(library.videos(folderId));
    }

    @PutMapping("/items/{id}")
    public ApiResponse<Video> updateVideo(@PathVariable long id, @Valid @RequestBody VideoUpdate request) {
        return ApiResponse.success(library.updateVideo(id, request));
    }

    @DeleteMapping("/items/{id}")
    public ApiResponse<Void> deleteVideo(@PathVariable long id) throws IOException {
        library.deleteVideo(id);
        return ApiResponse.success();
    }

    @PutMapping("/items/{id}/progress")
    public ApiResponse<Video> progress(@PathVariable long id, @Valid @RequestBody Progress request) {
        return ApiResponse.success(library.saveProgress(id, request));
    }

    @GetMapping("/items/{id}/playback")
    public ApiResponse<Playback> playback(@PathVariable long id) {
        return ApiResponse.success(library.playback(id));
    }

    @GetMapping("/storage/usage")
    public ApiResponse<StorageUsage> storageUsage() {
        return ApiResponse.success(library.usage());
    }

    @PostMapping("/uploads")
    public ApiResponse<UploadSession> initiate(@Valid @RequestBody UploadRequest request) {
        return ApiResponse.success(library.beginUpload(request));
    }

    @GetMapping("/uploads/{id}")
    public ApiResponse<UploadState> uploadState(@PathVariable String id) throws IOException {
        return ApiResponse.success(library.uploadStatus(id));
    }

    @PutMapping(value = "/uploads/{id}/parts/{number}", consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ApiResponse<Void> part(@PathVariable String id, @PathVariable int number,
                                  @RequestBody byte[] bytes) throws IOException {
        library.writeChunk(id, number, bytes);
        return ApiResponse.success();
    }

    @PostMapping("/uploads/{id}/complete")
    public ApiResponse<Video> complete(@PathVariable String id) throws IOException {
        return ApiResponse.success(library.completeUpload(id));
    }

    /**
     * Video elements cannot attach a Bearer header. This route accepts a short-lived
     * signed playback ticket, and rechecks the tenant's ownership on every range request.
     */
    @GetMapping("/media/{id}")
    public void media(@PathVariable long id, @RequestParam @NotBlank String ticket,
                      HttpServletRequest request, HttpServletResponse response) throws IOException {
        VideoLibraryService.MediaHandle media = library.authorizedMedia(id, ticket);
        response.setHeader("Cache-Control", "private, no-store");
        response.setHeader("Referrer-Policy", "no-referrer");
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setContentType("video/mp4");
        if (nginxDelivery) {
            // Nginx internal location alone serves the bytes and handles Range/HEAD.
            // NEVER accept the internal path from a request parameter.
            response.setHeader("X-Accel-Redirect", storage.internalRedirect(media.userId(), media.key()));
            return;
        }
        response.setHeader("Accept-Ranges", "bytes");
        long size = storage.mediaSize(media.userId(), media.key());

        String rangeHeader = request.getHeader("Range");
        ByteRanges.Span span;
        try {
            span = ByteRanges.parse(rangeHeader, size);
        } catch (IllegalArgumentException e) {
            response.setStatus(HttpServletResponse.SC_REQUESTED_RANGE_NOT_SATISFIABLE);
            response.setHeader("Content-Range", "bytes */" + size);
            return;
        }

        boolean partial = rangeHeader != null && !rangeHeader.isBlank();
        response.setStatus(partial ? HttpServletResponse.SC_PARTIAL_CONTENT : HttpServletResponse.SC_OK);
        if (partial) {
            response.setHeader("Content-Range",
                    "bytes " + span.start() + "-" + span.end() + "/" + size);
        }
        response.setContentLengthLong(span.length());
        if ("HEAD".equalsIgnoreCase(request.getMethod())) return;

        byte[] buffer = new byte[64 * 1024];
        try (SeekableByteChannel channel = storage.readMedia(media.userId(), media.key())) {
            channel.position(span.start());
            long remaining = span.length();
            while (remaining > 0) {
                ByteBuffer chunk = ByteBuffer.wrap(buffer, 0, (int) Math.min(buffer.length, remaining));
                int read = channel.read(chunk);
                if (read <= 0) break;
                response.getOutputStream().write(buffer, 0, read);
                remaining -= read;
            }
        }
    }
}

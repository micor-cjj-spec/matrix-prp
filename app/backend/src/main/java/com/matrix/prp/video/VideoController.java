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
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import org.springframework.context.annotation.Profile;
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

    public VideoController(VideoLibraryService library) {
        this.library = library;
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

    @PostMapping("/uploads")
    public ApiResponse<UploadSession> initiate(@Valid @RequestBody UploadRequest request) {
        return ApiResponse.success(library.beginUpload(request));
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
        Path path = library.authorizedMedia(id, ticket);
        long size = Files.size(path);
        response.setHeader("Cache-Control", "private, no-store");
        response.setHeader("Referrer-Policy", "no-referrer");
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setHeader("Accept-Ranges", "bytes");
        response.setContentType("video/mp4");

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
        try (SeekableByteChannel channel = Files.newByteChannel(path, StandardOpenOption.READ)) {
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

package com.matrix.prp.vocal;

import com.matrix.prp.common.api.ApiResponse;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("!test")
@RequestMapping("/api/vocal")
public class VocalLibraryController {
    private final VocalLibraryService service;
    public VocalLibraryController(VocalLibraryService service) { this.service = service; }

    @GetMapping("/songs")
    public ApiResponse<List<VocalLibraryService.Song>> songs() {
        return ApiResponse.success(service.songs());
    }
    @PostMapping("/songs")
    public ApiResponse<VocalLibraryService.Song> createSong(@RequestBody VocalLibraryService.SongRequest request) {
        return ApiResponse.success(service.createSong(request));
    }
    @PutMapping("/songs/{id}")
    public ApiResponse<VocalLibraryService.Song> updateSong(@PathVariable long id,
            @RequestBody VocalLibraryService.SongRequest request) {
        return ApiResponse.success(service.updateSong(id, request));
    }
    @DeleteMapping("/songs/{id}")
    public ApiResponse<Void> deleteSong(@PathVariable long id) {
        service.deleteSong(id); return ApiResponse.success();
    }

    @GetMapping("/songs/{songId}/sections")
    public ApiResponse<List<VocalLibraryService.Section>> sections(@PathVariable long songId) {
        return ApiResponse.success(service.sections(songId));
    }
    @PostMapping("/songs/{songId}/sections")
    public ApiResponse<VocalLibraryService.Section> createSection(@PathVariable long songId,
            @RequestBody VocalLibraryService.SectionRequest request) {
        return ApiResponse.success(service.createSection(songId, request));
    }
    @PutMapping("/sections/{id}")
    public ApiResponse<VocalLibraryService.Section> updateSection(@PathVariable long id,
            @RequestBody VocalLibraryService.SectionRequest request) {
        return ApiResponse.success(service.updateSection(id, request));
    }
    @DeleteMapping("/sections/{id}")
    public ApiResponse<Void> deleteSection(@PathVariable long id) {
        service.deleteSection(id); return ApiResponse.success();
    }

    @GetMapping("/lessons")
    public ApiResponse<List<VocalLibraryService.Lesson>> lessons() {
        return ApiResponse.success(service.lessons());
    }
    @PostMapping("/lessons")
    public ApiResponse<VocalLibraryService.Lesson> createLesson(@RequestBody VocalLibraryService.LessonRequest request) {
        return ApiResponse.success(service.createLesson(request));
    }
    @PutMapping("/lessons/{id}")
    public ApiResponse<VocalLibraryService.Lesson> updateLesson(@PathVariable long id,
            @RequestBody VocalLibraryService.LessonRequest request) {
        return ApiResponse.success(service.updateLesson(id, request));
    }
    @DeleteMapping("/lessons/{id}")
    public ApiResponse<Void> deleteLesson(@PathVariable long id) {
        service.deleteLesson(id); return ApiResponse.success();
    }

    @GetMapping("/assignments")
    public ApiResponse<List<VocalLibraryService.Assignment>> assignments() {
        return ApiResponse.success(service.assignments());
    }
    @PostMapping("/assignments")
    public ApiResponse<VocalLibraryService.Assignment> createAssignment(
            @RequestBody VocalLibraryService.AssignmentRequest request) {
        return ApiResponse.success(service.createAssignment(request));
    }
    @PutMapping("/assignments/{id}")
    public ApiResponse<VocalLibraryService.Assignment> updateAssignment(@PathVariable long id,
            @RequestBody VocalLibraryService.AssignmentRequest request) {
        return ApiResponse.success(service.updateAssignment(id, request));
    }
    @DeleteMapping("/assignments/{id}")
    public ApiResponse<Void> deleteAssignment(@PathVariable long id) {
        service.deleteAssignment(id); return ApiResponse.success();
    }
}

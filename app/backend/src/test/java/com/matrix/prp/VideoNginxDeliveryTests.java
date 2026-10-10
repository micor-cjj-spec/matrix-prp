package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

import com.matrix.prp.video.VideoController;
import com.matrix.prp.video.VideoLibraryService;
import com.matrix.prp.video.VideoStorage;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class VideoNginxDeliveryTests {
    @Test
    void sendsInternalRedirectOnlyAfterServiceAuthorizesTicketAndOwnership() throws Exception {
        VideoStorage storage = mock(VideoStorage.class);
        VideoLibraryService library = mock(VideoLibraryService.class);
        when(library.authorizedMedia(88L, "signed-ticket"))
                .thenReturn(new VideoLibraryService.MediaHandle(4L,
                        "af9c47ba-66df-4deb-88e3-3c7c840a5e88"));
        when(storage.internalRedirect(4L, "af9c47ba-66df-4deb-88e3-3c7c840a5e88"))
                .thenReturn("/_internal_prp_video/4/af9c47ba-66df-4deb-88e3-3c7c840a5e88.mp4");

        VideoController controller = new VideoController(library, storage, "nginx");
        var request = new MockHttpServletRequest("GET", "/api/video/media/88");
        request.addHeader("Range", "bytes=5-10");
        var response = new MockHttpServletResponse();
        controller.media(88, "signed-ticket", request, response);

        assertThat(response.getHeader("X-Accel-Redirect"))
                .isEqualTo("/_internal_prp_video/4/af9c47ba-66df-4deb-88e3-3c7c840a5e88.mp4");
        assertThat(response.getContentAsByteArray()).isEmpty();
        assertThat(response.getHeader("Cache-Control")).isEqualTo("private, no-store");
        verify(storage, never()).readMedia(anyLong(), anyString());
        verify(storage, never()).mediaSize(anyLong(), anyString());
    }

    @Test
    void rejectsUnconfiguredDeliveryMode() {
        assertThatThrownBy(() -> new VideoController(mock(VideoLibraryService.class),
                mock(VideoStorage.class), "public")).isInstanceOf(IllegalArgumentException.class);
    }
}

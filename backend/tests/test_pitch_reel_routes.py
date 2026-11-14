from unittest.mock import MagicMock, patch

from app.routes.pitch_reel_routes import stream_pitch_reel_video


def test_stream_pitch_reel_video_returns_full_content_without_range_header():
    mock_service = MagicMock()
    mock_service.get_reel_video_data.return_value = b"0123456789"

    with patch("app.routes.pitch_reel_routes.create_database_client", return_value=MagicMock()):
        with patch("app.routes.pitch_reel_routes.create_pitch_reel_service", return_value=mock_service):
            response = stream_pitch_reel_video("reel-1")

    assert response.status_code == 200
    assert response.body == b"0123456789"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == "10"


def test_stream_pitch_reel_video_honors_range_requests():
    mock_service = MagicMock()
    mock_service.get_reel_video_data.return_value = b"0123456789"

    with patch("app.routes.pitch_reel_routes.create_database_client", return_value=MagicMock()):
        with patch("app.routes.pitch_reel_routes.create_pitch_reel_service", return_value=mock_service):
            response = stream_pitch_reel_video("reel-1", range_header="bytes=2-5")

    assert response.status_code == 206
    assert response.body == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["content-length"] == "4"

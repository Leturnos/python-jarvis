from unittest.mock import MagicMock, patch

import numpy as np

from core.media.cv_matcher import TemplateMatcher


@patch("core.media.cv_matcher.pyautogui.screenshot")
@patch("core.media.cv_matcher.cv2.imread")
@patch("core.media.cv_matcher.cv2.cvtColor")
def test_locate_template_multiscale_success(mock_cvt, mock_imread, mock_screenshot):
    matcher = TemplateMatcher()
    mock_screenshot.return_value = MagicMock()
    mock_cvt.side_effect = [
        np.zeros((100, 100, 3), dtype=np.uint8),
        np.zeros((100, 100), dtype=np.uint8),
        np.zeros((10, 10), dtype=np.uint8),
    ]
    mock_imread.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

    with (
        patch("core.media.cv_matcher.cv2.matchTemplate") as mock_match,
        patch("core.media.cv_matcher.cv2.minMaxLoc") as mock_minmax,
    ):
        mock_match.return_value = np.array([[0.9]], dtype=np.float32)
        mock_minmax.return_value = (0.1, 0.9, (0, 0), (0, 0))
        res = matcher.locate_template_multiscale("dummy.png", confidence=0.7)
        assert res is not None
        assert res.width == 10

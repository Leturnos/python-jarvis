from collections import namedtuple
from typing import Any

import cv2
import numpy as np
import pyautogui

from core.infra.logger_config import logger

Box = namedtuple("Box", ["left", "top", "width", "height"])


class TemplateMatcher:
    def locate_template_multiscale(
        self,
        template_path: str,
        region: tuple[int, int, int, int] | None = None,
        confidence: float = 0.7,
    ) -> Any:
        try:
            screenshot = pyautogui.screenshot(region=region)
            haystack = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            haystack_gray = cv2.cvtColor(haystack, cv2.COLOR_BGR2GRAY)

            template = cv2.imread(template_path)
            if template is None:
                logger.error(f"Template not found at: {template_path}")
                return None
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            best_val = -1.0
            best_loc = None
            best_scale = None

            w = template_gray.shape[1]
            h = template_gray.shape[0]
            if w <= haystack_gray.shape[1] and h <= haystack_gray.shape[0]:
                res = cv2.matchTemplate(
                    haystack_gray, template_gray, cv2.TM_CCOEFF_NORMED
                )
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val >= confidence:
                    best_val = max_val
                    best_loc = max_loc
                    best_scale = 1.0

            if best_val < confidence:
                scales = [0.9, 1.1, 1.25, 0.8]
                for scale in scales:
                    w = int(template_gray.shape[1] * scale)
                    h = int(template_gray.shape[0] * scale)
                    if (
                        w > haystack_gray.shape[1]
                        or h > haystack_gray.shape[0]
                        or w < 10
                        or h < 10
                    ):
                        continue
                    resized = cv2.resize(template_gray, (w, h))
                    res = cv2.matchTemplate(
                        haystack_gray, resized, cv2.TM_CCOEFF_NORMED
                    )
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val > best_val:
                        best_val = max_val
                        best_loc = max_loc
                        best_scale = scale

            if best_val >= confidence and best_loc is not None:
                w = int(template_gray.shape[1] * best_scale)
                h = int(template_gray.shape[0] * best_scale)
                left_rel, top_rel = best_loc
                region_left = region[0] if region else 0
                region_top = region[1] if region else 0
                return Box(region_left + left_rel, region_top + top_rel, w, h)
        except Exception as e:
            logger.error(f"Error in template matching: {e}")
        return None

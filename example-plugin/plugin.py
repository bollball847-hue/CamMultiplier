"""Example plugin: turns one copy into a black-and-white picture."""
import cv2


class GrayscalePlugin:
    def __init__(self, api):
        self.api = api
        # Setting "copy" (1 = first copy). Change it by editing the settings or add a settings_ui.
        self.copy = int(api.get_setting("copy", 2))

    def on_start(self, info):
        self.api.log(f"grayscale on copy {self.copy} of {info['copies']}")

    def on_frame(self, copy_index, frame):
        if copy_index + 1 != self.copy:
            return None  # unchanged
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)  # return a NEW frame, never edit 'frame' itself

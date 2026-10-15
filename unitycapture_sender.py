"""
Sender for the Unity Capture virtual camera driver (Windows, DirectShow).

Cam Multiplier talks to the driver directly through the shared memory it provides, so no extra
Python package is needed. The driver (UnityCaptureFilter32/64.dll) is by Bernhard Schelling
(MIT license): https://github.com/schellingb/UnityCapture

How it works: the driver creates a named mutex, two named events and a named shared memory
block for every virtual camera ("UnityCapture_Mutx", "_Want", "_Sent", "_Data", followed by the
camera number for cameras 2, 3, ...). We open these objects, write a small header (size, format)
and the RGBA picture into the shared memory, and signal the "Sent" event.
The objects only exist while an application (OBS, Discord, ...) has the virtual camera open, so
send() simply returns False until then.
"""
import ctypes
import re

HEADER_FIELDS = [("maxSize", ctypes.c_uint32), ("width", ctypes.c_int), ("height", ctypes.c_int),
                 ("stride", ctypes.c_int), ("format", ctypes.c_int), ("resizemode", ctypes.c_int),
                 ("mirrormode", ctypes.c_int), ("timeout", ctypes.c_int)]


class _Header(ctypes.Structure):
    _fields_ = HEADER_FIELDS


HEADER_SIZE = ctypes.sizeof(_Header)  # the picture data follows directly after the header

SYNCHRONIZE = 0x00100000
EVENT_MODIFY_STATE = 0x0002
FILE_MAP_WRITE = 0x0002
WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 0x80
FORMAT_UINT8 = 0       # 8 bit RGBA
RESIZEMODE_LINEAR = 1  # the driver scales the picture to the size the application asked for
LOCK_TIMEOUT_MS = 500

_kernel32 = None


def _k32():
    global _kernel32
    if _kernel32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        h, d, b, s = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_char_p
        for name, args, res in [
            ("OpenMutexA", [d, b, s], h), ("OpenEventA", [d, b, s], h),
            ("CreateEventA", [ctypes.c_void_p, b, b, s], h), ("OpenFileMappingA", [d, b, s], h),
            ("MapViewOfFile", [h, d, d, d, ctypes.c_size_t], ctypes.c_void_p),
            ("UnmapViewOfFile", [ctypes.c_void_p], b), ("WaitForSingleObject", [h, d], d),
            ("ReleaseMutex", [h], b), ("SetEvent", [h], b), ("CloseHandle", [h], b)]:
            fn = getattr(k, name)
            fn.argtypes, fn.restype = args, res
        _kernel32 = k
    return _kernel32


def capnum_from_name(name):
    """'Cam Multiplier' -> 0, 'Cam Multiplier #2' -> 1 (the driver numbers its cameras like this)."""
    m = re.search(r" #(\d+)$", name)
    return max(0, int(m.group(1)) - 1) if m else 0


class VirtualCamera:
    def __init__(self, cap_num):
        suffix = chr(ord("0") + cap_num) if cap_num else ""
        self._names = {k: (f"UnityCapture_{k}{suffix}").encode() for k in ("Mutx", "Want", "Sent", "Data")}
        self._mutex = self._want = self._sent = self._file = self._ptr = None

    def _open(self):
        """Opens the shared objects step by step (like the original sender); False until all exist."""
        if self._ptr:
            return True
        k = _k32()
        if not self._mutex:
            self._mutex = k.OpenMutexA(SYNCHRONIZE, 0, self._names["Mutx"])
            if not self._mutex:
                return False
        if k.WaitForSingleObject(self._mutex, LOCK_TIMEOUT_MS) not in (WAIT_OBJECT_0, WAIT_ABANDONED):
            return False
        try:
            if not self._want:
                self._want = k.CreateEventA(None, 0, 0, self._names["Want"])
                if not self._want:
                    return False
            if not self._sent:
                self._sent = k.OpenEventA(EVENT_MODIFY_STATE, 0, self._names["Sent"])
                if not self._sent:
                    return False
            if not self._file:
                self._file = k.OpenFileMappingA(FILE_MAP_WRITE, 0, self._names["Data"])
                if not self._file:
                    return False
            self._ptr = k.MapViewOfFile(self._file, FILE_MAP_WRITE, 0, 0, 0)
            return bool(self._ptr)
        finally:
            k.ReleaseMutex(self._mutex)

    def send(self, rgba):
        """rgba: numpy array (height, width, 4), uint8, C-contiguous. Returns True if the picture was delivered."""
        if not self._open():
            return False
        height, width = rgba.shape[:2]
        size = width * height * 4
        hdr = _Header.from_address(self._ptr)
        if hdr.maxSize < size:
            return False
        k = _k32()
        if k.WaitForSingleObject(self._mutex, LOCK_TIMEOUT_MS) not in (WAIT_OBJECT_0, WAIT_ABANDONED):
            return False
        try:
            hdr.width, hdr.height, hdr.stride = width, height, width  # stride counts pixels
            hdr.format, hdr.resizemode, hdr.mirrormode, hdr.timeout = FORMAT_UINT8, RESIZEMODE_LINEAR, 0, 1000
            ctypes.memmove(self._ptr + HEADER_SIZE, rgba.ctypes.data, size)
        finally:
            k.ReleaseMutex(self._mutex)
        k.SetEvent(self._sent)
        return True

    def close(self):
        k = _k32()
        if self._ptr:
            k.UnmapViewOfFile(self._ptr)
        for h in (self._mutex, self._want, self._sent, self._file):
            if h:
                k.CloseHandle(h)
        self._mutex = self._want = self._sent = self._file = self._ptr = None

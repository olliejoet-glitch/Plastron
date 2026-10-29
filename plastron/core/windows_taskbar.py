"""Windows taskbar: Plastron's own button and icon.

Blender's windows carry Blender's identity, so the taskbar shows Blender's
icon and groups Plastron with any other Blender that's open. Here each
Plastron window gets its own App User Model ID (its own taskbar group), the
Plastron icon, and a relaunch command, so pinning it pins the launcher.
Windows only; does nothing elsewhere and never stops Plastron starting.
"""

import os
import sys

import bpy

APP_ID = "Plastron.App"
DISPLAY_NAME = "Plastron"


def _paths():
    """(launcher folder root, icon path). Root is C:\\Plastron for Ollie's install."""
    root = os.path.dirname(os.path.dirname(bpy.app.binary_path))
    icon = os.path.join(root, "plastron.ico")
    if not os.path.exists(icon):
        icon = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "assets", "plastron.ico")
    return root, icon


def _apply_windows():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    kernel32 = ctypes.WinDLL("kernel32")

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    class PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                    ("r3", ctypes.c_ushort), ("ptr", ctypes.c_void_p), ("ptr2", ctypes.c_void_p)]

    def guid(text):
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(g))
        return g

    VT_LPWSTR = 31
    IID_IPropertyStore = guid("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")
    APPUSERMODEL = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"
    PID_RELAUNCH_COMMAND, PID_RELAUNCH_ICON, PID_RELAUNCH_NAME, PID_ID = 2, 3, 4, 5

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    shell32.SHGetPropertyStoreForWindow.argtypes = [wintypes.HWND, ctypes.POINTER(GUID),
                                                    ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long

    pid = kernel32.GetCurrentProcessId()
    hwnds = []

    @WNDENUMPROC
    def collect(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            hwnds.append(hwnd)
        return True

    user32.EnumWindows(collect, 0)

    root, icon = _paths()
    launcher = os.path.join(root, "launch.ps1")
    command = ('powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%s"'
               % launcher) if os.path.exists(launcher) else ""
    values = [(PID_RELAUNCH_ICON, icon), (PID_RELAUNCH_NAME, DISPLAY_NAME)]
    if command:
        values.append((PID_RELAUNCH_COMMAND, command))
    values.append((PID_ID, APP_ID))       # set last: it makes the taskbar regroup

    LR_LOADFROMFILE, IMAGE_ICON, WM_SETICON = 0x10, 1, 0x0080
    big = user32.LoadImageW(None, icon, IMAGE_ICON, user32.GetSystemMetrics(11),
                            user32.GetSystemMetrics(12), LR_LOADFROMFILE)
    small = user32.LoadImageW(None, icon, IMAGE_ICON, user32.GetSystemMetrics(49),
                              user32.GetSystemMetrics(50), LR_LOADFROMFILE)

    ole32.CoInitialize(None)
    for hwnd in hwnds:
        if big:
            user32.SendMessageW(hwnd, WM_SETICON, 1, big)
        if small:
            user32.SendMessageW(hwnd, WM_SETICON, 0, small)
        store = ctypes.c_void_p()
        if shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(IID_IPropertyStore),
                                               ctypes.byref(store)) != 0 or not store:
            continue
        vtable = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        set_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY),
                                       ctypes.POINTER(PROPVARIANT))(vtable[6])
        commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable[7])
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
        try:
            for prop_id, text in values:
                key = PROPERTYKEY(guid(APPUSERMODEL), prop_id)
                buf = ctypes.create_unicode_buffer(text)     # the store copies it
                value = PROPVARIANT(vt=VT_LPWSTR, ptr=ctypes.addressof(buf))
                set_value(store, ctypes.byref(key), ctypes.byref(value))
            commit(store)
        finally:
            release(store)
    return len(hwnds)


def apply(*_args):
    if sys.platform != "win32":
        return None
    try:
        _apply_windows()
    except Exception as err:          # cosmetic: never break Plastron over it
        print("Plastron: couldn't set the taskbar icon:", err)
    return None


def register():
    if sys.platform == "win32":
        # The window exists once startup has finished.
        bpy.app.timers.register(apply, first_interval=0.5, persistent=True)
        from . import handlers
        handlers.on_load(_after_load)


def _after_load(_scene):
    if not bpy.app.timers.is_registered(apply):
        bpy.app.timers.register(apply, first_interval=0.5)


def unregister():
    if bpy.app.timers.is_registered(apply):
        bpy.app.timers.unregister(apply)

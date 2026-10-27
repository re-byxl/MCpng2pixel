"""在服务器端弹出系统目录选择框。

单独作为进程运行，避免在 HTTP 服务线程里调用 Tk 引发的问题。
用法：``python -m pixelmatic.tool.dialog <起始目录>``
选中的路径打印到标准输出。
"""

from __future__ import annotations

import sys


def _enable_windows_dpi_awareness() -> None:
    """声明 DPI 感知，否则高分屏（缩放 >100%）下选择框会被系统拉伸发糊。

    本模块总是以独立子进程运行，进程级设置随进程结束消失，不影响调用方。
    """
    if sys.platform != "win32":
        return

    import ctypes

    try:
        # Per-Monitor v2（Win10 1703+）；不存在时逐级退回旧接口
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog

    _enable_windows_dpi_awareness()
    start = sys.argv[1] if len(sys.argv) > 1 else "."

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.update()

    path = filedialog.askdirectory(
        initialdir=start,
        mustexist=False,
        title="选择文件夹",
    )
    root.destroy()

    if path:
        # stdout 是与 server.py 之间的 IPC 协议通道（server 起子进程读 stdout 拿路径），
        # 必须用 print，不能改成 logging
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

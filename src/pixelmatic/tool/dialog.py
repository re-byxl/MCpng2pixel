"""在服务器端弹出系统目录选择框。

单独作为进程运行，避免在 HTTP 服务线程里调用 Tk 引发的问题。
用法：``python -m pixelmatic.tool.dialog <起始目录>``
选中的路径打印到标准输出。
"""

from __future__ import annotations

import sys


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog

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

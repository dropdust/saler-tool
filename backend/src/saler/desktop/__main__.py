"""`python -m saler.desktop` 入口（同时作为 PyInstaller 冻结入口）。"""

import multiprocessing

from saler.desktop.app import main

if __name__ == "__main__":
    # 冻结包：先 freeze_support，避免子进程（若有）重复启动窗体
    multiprocessing.freeze_support()
    raise SystemExit(main())

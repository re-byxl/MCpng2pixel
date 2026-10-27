"""本地网页前端所用的 HTTP 服务。

只用标准库实现，前端是 ``mcyqqs/tool/web/`` 下的静态页面。

纯领域逻辑（变换、投影、预览）都在 :mod:`mcyqqs.litematic.core` 里，
这个模块只负责 HTTP 层的收发和 JSON 组装。
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..litematic.core import (
    TransformPlan,
    collect_block_names,
    list_input_files,
    load_region,
    preview_file,
    resolve_output_path,
    transform_file,
)
from ..matching.palette import MC_BLOCKS
from . import PROJECT_ROOT, SETTINGS_FILENAME, resolve_path

#: ``src`` 目录的绝对路径（源码方式运行时让子进程也能 import 到 mcyqqs）
SRC_ROOT = str(Path(__file__).resolve().parents[2])

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #


def _default_tool_settings() -> dict:
    """工具配置的默认值。

    优先用新的配置模型（``config.json`` 的 ``tool`` 节），
    配置模型还不可用时退回到内置默认值。
    """
    try:
        from ..config import AppConfig

        tool = AppConfig().tool
        return {
            "input_dir": str(tool.input_dir),
            "output_dir": str(tool.output_dir),
            "suffix": str(tool.suffix),
            "overwrite": bool(tool.overwrite),
            "keep_properties": bool(tool.keep_properties),
            "plan": tool.plan.to_dict(),
            "replacements": dict(tool.replacements),
        }
    except Exception:
        return {
            "input_dir": "input_litematic",
            "output_dir": "output/litematic_transformed",
            "suffix": "_transformed",
            "overwrite": True,
            "keep_properties": False,
            "plan": TransformPlan().to_dict(),
            "replacements": {"red_concrete": "red_terracotta"},
        }


#: 允许保存的配置字段
KNOWN_SETTING_KEYS = (
    "input_dir",
    "output_dir",
    "suffix",
    "overwrite",
    "keep_properties",
    "plan",
    "replacements",
)

#: 当前使用的配置文件路径
_settings_path: Path = Path(PROJECT_ROOT) / SETTINGS_FILENAME

#: 旧版的工具配置文件名（``tool`` 节还没并进 config.json 时用）
LEGACY_SETTINGS_FILENAME = "litematic_tool.json"


def _read_raw_settings(path: Path) -> dict:
    """读一个配置文件，返回原始 dict（读不到 / 坏了就空 dict）。"""
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _is_legacy_settings(raw: dict) -> bool:
    """判断一个配置文件是不是旧版"扁平"的工具配置。"""
    if not raw or "tool" in raw:
        return False
    return any(key in raw for key in KNOWN_SETTING_KEYS)


def _tool_settings_from_raw(raw: dict) -> dict:
    """把旧版扁平配置整理成工具配置（纯 dict）。"""
    defaults = _default_tool_settings()
    merged = dict(defaults)
    merged.update({key: raw[key] for key in KNOWN_SETTING_KEYS if key in raw})
    merged["plan"] = TransformPlan.from_dict(
        {**defaults["plan"], **(merged.get("plan") or {})}
    ).to_dict()
    if not isinstance(merged.get("replacements"), dict):
        merged["replacements"] = dict(defaults["replacements"])
    return merged


def _load_tool_settings(path: str | Path | None = None) -> dict:
    """读取工具配置。

    默认读 ``config.json`` 的 ``tool`` 节；旧版扁平的 ``litematic_tool.json``
    也照样认 —— 显式把路径传进来时按旧格式读，默认路径下如果 config.json
    里没有 ``tool`` 节就自动回退到旧文件。

    返回的是纯 dict（和前端 / 命令行期望的形状一致）。
    """
    target = Path(path) if path else _settings_path

    raw = _read_raw_settings(target)
    if _is_legacy_settings(raw):
        return _tool_settings_from_raw(raw)

    if path is None:
        legacy_raw = _read_raw_settings(Path(PROJECT_ROOT) / LEGACY_SETTINGS_FILENAME)
        if _is_legacy_settings(legacy_raw):
            return _tool_settings_from_raw(legacy_raw)

    from ..config import AppConfig, load_config

    try:
        config = load_config(target)
    except Exception:
        config = AppConfig()

    tool = config.tool
    return {
        "input_dir": str(tool.input_dir),
        "output_dir": str(tool.output_dir),
        "suffix": tool.suffix,
        "overwrite": bool(tool.overwrite),
        "keep_properties": bool(tool.keep_properties),
        "plan": tool.plan.to_dict(),
        "replacements": dict(tool.replacements),
    }


def _save_tool_settings(data: dict, path: str | Path | None = None) -> None:
    """保存工具配置（原子写入）。

    目标是新配置就写回 ``config.json`` 的 ``tool`` 节；
    目标是旧版扁平文件就按旧格式整体替换。
    """
    target = Path(path) if path else _settings_path

    defaults = _default_tool_settings()
    merged = {key: (data or {}).get(key, defaults[key]) for key in KNOWN_SETTING_KEYS}
    merged["plan"] = TransformPlan.from_dict(
        {**defaults["plan"], **(merged.get("plan") or {})}
    ).to_dict()
    if not isinstance(merged.get("replacements"), dict):
        merged["replacements"] = {}

    if _is_legacy_settings(_read_raw_settings(target)):
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return

    from ..config import AppConfig, ToolConfig, load_config, save_config

    try:
        config = load_config(target)
    except Exception:
        config = AppConfig()

    config.tool = ToolConfig.model_validate(merged)
    save_config(config, target)


#: 当前生效的工具配置（模块级）
settings: dict = _load_tool_settings()


def current_settings() -> dict:
    """返回当前配置。

    和旧的 ``SettingsStore.load()`` 一样，每次都重新读盘，
    这样在外部改了配置文件也能立刻生效。
    """
    fresh = _load_tool_settings()
    settings.clear()
    settings.update(fresh)
    return settings


# --------------------------------------------------------------------------- #
# 任务
# --------------------------------------------------------------------------- #


class Job:
    def __init__(self) -> None:
        self.id = uuid.uuid4().hex
        self.status = "running"
        self.log: list[str] = []
        self.results: list[dict] = []
        self.lock = threading.Lock()

    def write(self, message: str) -> None:
        with self.lock:
            self.log.append(message)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "status": self.status,
                "log": list(self.log),
                "results": list(self.results),
            }


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def create(self) -> Job:
        job = Job()
        with self.lock:
            self.jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)


# --------------------------------------------------------------------------- #
# 请求处理
# --------------------------------------------------------------------------- #


class Handler(BaseHTTPRequestHandler):
    server_version = "LitematicTool/1.0"

    # 由 create_server 注入
    settings_path: Path
    jobs: JobManager

    # ------------------------------------------------------------------ #

    def log_message(self, fmt, *args):  # 静音默认的访问日志
        pass

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str) -> None:
        if not os.path.isfile(path):
            self._send_json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ #

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        if route in ("/", "/index.html"):
            self._send_file(os.path.join(WEB_DIR, "index.html"))
        elif route in ("/app.js", "/style.css"):
            self._send_file(os.path.join(WEB_DIR, route.lstrip("/")))
        elif route == "/api/state":
            self._handle_state()
        elif route == "/api/job":
            job_id = (query.get("id") or [""])[0]
            job = self.jobs.get(job_id)
            if not job:
                self._send_json({"error": "job not found"}, 404)
                return
            self._send_json(job.snapshot())
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        try:
            if route == "/api/settings":
                self._handle_save_settings()
            elif route == "/api/preview":
                self._handle_preview()
            elif route == "/api/transform":
                self._handle_transform()
            elif route == "/api/browse":
                self._handle_browse()
            elif route == "/api/open_folder":
                self._handle_open_folder()
            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as exc:
            self._send_json({"error": f"{exc}", "trace": traceback.format_exc()}, 500)

    # ------------------------------------------------------------------ #

    def _handle_state(self) -> None:
        config = current_settings()
        input_dir = resolve_path(config.get("input_dir", ""))
        output_dir = resolve_path(config.get("output_dir", ""))
        files = list_input_files(input_dir)

        blocks: set[str] = set()
        for entry in files:
            if entry.get("error"):
                continue
            with contextlib.suppress(Exception):
                region, _ = load_region(entry["path"])
                blocks |= collect_block_names(region)

        with contextlib.suppress(Exception):
            blocks |= set(MC_BLOCKS.keys())

        self._send_json(
            {
                "settings": config,
                "input_dir": input_dir,
                "output_dir": output_dir,
                "project_root": str(PROJECT_ROOT),
                "files": files,
                "blocks": sorted(blocks),
            }
        )

    def _handle_save_settings(self) -> None:
        data = self._read_json()
        _save_tool_settings(data, self.settings_path)
        saved = current_settings()
        self._send_json({"settings": saved})

    def _handle_preview(self) -> None:
        data = self._read_json()
        config = current_settings()
        plan = TransformPlan.from_dict(data.get("plan") or config.get("plan"))

        name = str(data.get("file") or "")
        input_dir = resolve_path(data.get("input_dir") or config.get("input_dir", ""))
        path = os.path.normpath(os.path.join(input_dir, name))
        if not _is_inside(path, input_dir):
            self._send_json({"error": "非法路径"}, 400)
            return
        if not os.path.isfile(path):
            self._send_json({"error": "文件不存在"}, 404)
            return

        replacements = data.get("replacements")
        if not isinstance(replacements, dict):
            replacements = config.get("replacements", {})

        payload = preview_file(path, plan, str(data.get("view") or "both"), replacements)
        payload["file"] = name
        self._send_json(payload)

    def _handle_transform(self) -> None:
        data = self._read_json()
        config = current_settings()

        plan = TransformPlan.from_dict(data.get("plan") or config.get("plan"))
        replacements = data.get("replacements")
        if not isinstance(replacements, dict):
            replacements = config.get("replacements", {})
        keep_properties = bool(data.get("keep_properties", config.get("keep_properties", False)))
        suffix = str(data.get("suffix", config.get("suffix", "_transformed")))
        overwrite = bool(data.get("overwrite", config.get("overwrite", True)))

        input_dir = resolve_path(data.get("input_dir") or config.get("input_dir", ""))
        output_dir = resolve_path(data.get("output_dir") or config.get("output_dir", ""))

        names = data.get("files") or []
        if not isinstance(names, list):
            names = []

        job = self.jobs.create()

        def run() -> None:
            used: set[str] = set()
            try:
                os.makedirs(output_dir, exist_ok=True)
                for name in names:
                    path = os.path.normpath(os.path.join(input_dir, str(name)))
                    if not _is_inside(path, input_dir):
                        job.write(f"[跳过] 非法路径: {name}")
                        continue
                    if not os.path.isfile(path):
                        job.write(f"[跳过] 文件不存在: {name}")
                        continue

                    out_path = resolve_output_path(output_dir, path, suffix, used)
                    out_name = os.path.basename(out_path)

                    if os.path.exists(out_path) and not overwrite:
                        job.write(f"[跳过] 已存在且未开启覆盖: {out_name}")
                        continue

                    job.write(f"[处理中] {name}")
                    summary = transform_file(path, out_path, plan, replacements, keep_properties)
                    for region in summary["regions"]:
                        dims = region["dims"]
                        job.write(
                            f"    → {out_name} 区域 {region['name']} "
                            f"{dims[0]}x{dims[1]}x{dims[2]}（{region['blocks']} 方块）"
                        )
                    job.results.append(summary)
                job.status = "done"
                job.write("[完成] 全部处理结束")
            except Exception as exc:
                job.status = "error"
                job.write(f"[错误] {exc}")
                job.write(traceback.format_exc())

        threading.Thread(target=run, daemon=True).start()
        self._send_json({"job": job.id})

    def _handle_browse(self) -> None:
        """在服务器端弹出一个系统目录选择框。"""
        data = self._read_json()
        start = resolve_path(str(data.get("start") or PROJECT_ROOT))
        try:
            env = dict(os.environ)
            paths = [SRC_ROOT, str(PROJECT_ROOT)]
            if env.get("PYTHONPATH"):
                paths.append(env["PYTHONPATH"])
            env["PYTHONPATH"] = os.pathsep.join(paths)
            proc = subprocess.run(
                [sys.executable, "-m", "mcyqqs.tool.dialog", start],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            chosen = (proc.stdout or "").strip().splitlines()
            path = chosen[-1].strip() if chosen else ""
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)
            return
        self._send_json({"path": path})

    def _handle_open_folder(self) -> None:
        data = self._read_json()
        path = resolve_path(str(data.get("path") or ""))
        if not path:
            self._send_json({"error": "路径为空"}, 400)
            return
        os.makedirs(path, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)
            return
        self._send_json({"ok": True, "path": path})


def _is_inside(path: str, parent: str) -> bool:
    """检查 path 是否位于 parent 目录内（防止路径穿越）。"""
    try:
        parent_real = os.path.realpath(parent)
        path_real = os.path.realpath(path)
    except Exception:
        return False
    if path_real == parent_real:
        return True
    return path_real.startswith(parent_real + os.sep)


# --------------------------------------------------------------------------- #
# 启动
# --------------------------------------------------------------------------- #


def create_server(
    host: str = "127.0.0.1", port: int = 8765, settings_path: str | None = None
) -> ThreadingHTTPServer:
    """创建（但不启动）HTTP 服务。"""
    global _settings_path

    _settings_path = (
        Path(settings_path) if settings_path else Path(PROJECT_ROOT) / SETTINGS_FILENAME
    )
    Handler.settings_path = _settings_path
    Handler.jobs = JobManager()
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = "127.0.0.1", port: int = 8765, settings_path: str | None = None) -> None:
    httpd = create_server(host, port, settings_path)
    print(f"Litematic 工具已启动: http://{host}:{port}")
    print("按 Ctrl+C 结束。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()

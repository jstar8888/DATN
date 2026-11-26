import json
import os
import re
import shutil
from pathlib import Path
from threading import Lock
from typing import Any


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
RELATIONSHIP_CONFIG_DIR = CONFIG_DIR / "table_relationships"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "table_relationships_and_paths.json"
ACTIVE_CONFIG_PATH = RELATIONSHIP_CONFIG_DIR / "active.json"
_config_lock = Lock()


def _validate_config(config: Any) -> None:
  if not isinstance(config, dict):
    raise ValueError("Cấu hình relationship phải là một object JSON.")

  nodes = config.get("nodes")
  edges = config.get("edges")
  if not isinstance(nodes, list) or not nodes:
    raise ValueError("Cấu hình relationship phải có danh sách nodes.")
  if not isinstance(edges, list):
    raise ValueError("Cấu hình relationship phải có danh sách edges.")

  node_ids = set()
  for node in nodes:
    if not isinstance(node, dict) or not all(
        isinstance(node.get(key), str) and node[key].strip()
        for key in ("id", "display_name", "table_name", "description")
    ):
      raise ValueError("Thông tin node trong cấu hình relationship không hợp lệ.")
    if node["id"] != node["table_name"]:
      raise ValueError("Node id phải trùng tên bảng.")
    if node["id"] in node_ids:
      raise ValueError(f"Node id bị trùng: {node['id']}.")
    node_ids.add(node["id"])

  for edge in edges:
    if (
        not isinstance(edge, dict)
        or edge.get("source") not in node_ids
        or edge.get("target") not in node_ids
        or not isinstance(edge.get("label"), str)
        or not edge["label"].strip()
        or not isinstance(edge.get("relationship_type"), str)
        or not isinstance(edge.get("join_condition"), dict)
        or not all(
            isinstance(edge["join_condition"].get(key), str)
            and edge["join_condition"][key].strip()
            for key in ("from_column", "to_column")
        )
    ):
      raise ValueError("Thông tin edge trong cấu hình relationship không hợp lệ.")


def _read_config(path: Path) -> dict[str, Any]:
  try:
    with path.open(encoding="utf-8") as config_file:
      config = json.load(config_file)
  except (OSError, json.JSONDecodeError) as exc:
    raise RuntimeError(f"Không thể đọc cấu hình relationship: {path}") from exc
  _validate_config(config)
  return config


def _managed_config_path(filename: str) -> Path:
  if (
      not isinstance(filename, str)
      or Path(filename).name != filename
      or "/" in filename
      or "\\" in filename
      or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]*\.json", filename)
      or filename.lower() == ACTIVE_CONFIG_PATH.name
  ):
    raise ValueError("Tên file không hợp lệ. Chỉ chấp nhận tên file .json.")
  return RELATIONSHIP_CONFIG_DIR / filename


def _ensure_relationship_config() -> None:
  RELATIONSHIP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
  config_files = [
      path
      for path in RELATIONSHIP_CONFIG_DIR.glob("*.json")
      if path.name != ACTIVE_CONFIG_PATH.name
  ]
  if not config_files:
    _read_config(DEFAULT_CONFIG_PATH)
    shutil.copy2(
        DEFAULT_CONFIG_PATH,
        RELATIONSHIP_CONFIG_DIR / DEFAULT_CONFIG_PATH.name,
    )

  if not ACTIVE_CONFIG_PATH.exists():
    default_filename = DEFAULT_CONFIG_PATH.name
    active_filename = (
        default_filename
        if (RELATIONSHIP_CONFIG_DIR / default_filename).exists()
        else sorted(config_files)[0].name
    )
    ACTIVE_CONFIG_PATH.write_text(
        json.dumps({"filename": active_filename}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def list_relationship_configs() -> dict[str, Any]:
  with _config_lock:
    _ensure_relationship_config()
    files = sorted(
        path.name
        for path in RELATIONSHIP_CONFIG_DIR.glob("*.json")
        if path.name != ACTIVE_CONFIG_PATH.name
    )
    try:
      with ACTIVE_CONFIG_PATH.open(encoding="utf-8") as active_file:
        active_data = json.load(active_file)
    except (OSError, json.JSONDecodeError) as exc:
      raise RuntimeError("Không thể đọc file relationship đang áp dụng.") from exc

    active_filename = (
        active_data.get("filename") if isinstance(active_data, dict) else None
    )
    if active_filename not in files:
      raise RuntimeError("File relationship đang áp dụng không tồn tại.")
    _read_config(_managed_config_path(active_filename))
    return {"files": files, "active_file": active_filename}


def add_relationship_config(filename: str, content: bytes) -> list[str]:
  path = _managed_config_path(filename)
  try:
    config = json.loads(content.decode("utf-8-sig"))
  except (UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise ValueError("File tải lên không phải JSON hợp lệ.") from exc
  _validate_config(config)

  with _config_lock:
    _ensure_relationship_config()
    if path.exists() or any(
        existing.name.casefold() == filename.casefold()
        for existing in RELATIONSHIP_CONFIG_DIR.glob("*.json")
    ):
      raise FileExistsError(f"File {filename} đã tồn tại.")
    temporary_path = path.with_suffix(".tmp")
    try:
      temporary_path.write_text(
          json.dumps(config, ensure_ascii=False, indent=2) + "\n",
          encoding="utf-8",
      )
      os.replace(temporary_path, path)
    except OSError:
      temporary_path.unlink(missing_ok=True)
      raise
    return sorted(
        item.name
        for item in RELATIONSHIP_CONFIG_DIR.glob("*.json")
        if item.name != ACTIVE_CONFIG_PATH.name
    )


def set_active_relationship_config(filename: str) -> str:
  path = _managed_config_path(filename)
  with _config_lock:
    _ensure_relationship_config()
    if not path.is_file():
      raise FileNotFoundError(f"Không tìm thấy file {filename}.")
    _read_config(path)

    temporary_path = ACTIVE_CONFIG_PATH.with_suffix(".tmp")
    try:
      temporary_path.write_text(
          json.dumps({"filename": filename}, ensure_ascii=False, indent=2)
          + "\n",
          encoding="utf-8",
      )
      os.replace(temporary_path, ACTIVE_CONFIG_PATH)
    except OSError:
      temporary_path.unlink(missing_ok=True)
      raise
  return filename


def get_active_relationship_config_path() -> Path:
  with _config_lock:
    _ensure_relationship_config()
    try:
      with ACTIVE_CONFIG_PATH.open(encoding="utf-8") as active_file:
        active_data = json.load(active_file)
    except (OSError, json.JSONDecodeError) as exc:
      raise RuntimeError("Không thể đọc file relationship đang áp dụng.") from exc

    filename = (
        active_data.get("filename") if isinstance(active_data, dict) else None
    )
    path = _managed_config_path(filename)
    if not path.is_file():
      raise RuntimeError("File relationship đang áp dụng không tồn tại.")
    _read_config(path)
    return path

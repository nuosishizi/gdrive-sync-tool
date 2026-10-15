import os
import re
import subprocess


def get_safe_path(path: str) -> str:
    r"""
    处理 Windows 下的长路径问题 (绕过 MAX_PATH 260 字符限制)
    返回带有 \\?\ 前缀的绝对路径。
    """
    if os.name != 'nt' or not path:
        return path
        
    abs_path = os.path.abspath(path)
    
    # 网络共享路径 \\server\share 需要转换为 \\?\UNC\server\share
    if abs_path.startswith('\\\\') and not abs_path.startswith('\\\\?\\'):
        return '\\\\?\\UNC\\' + abs_path[2:]
        
    # 普通本地路径 C:\a\b 转为 \\?\C:\a\b
    if not abs_path.startswith('\\\\?\\'):
        return '\\\\?\\' + abs_path
        
    return abs_path


def _strip_long_path_prefix(path: str) -> str:
    r"""移除 Windows \\?\ 前缀以便进行标准路径对比"""
    if path.startswith('\\\\?\\UNC\\'):
        return '\\\\' + path[8:]
    if path.startswith('\\\\?\\'):
        return path[4:]
    return path


_WIN_RESERVED_RE = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$', re.IGNORECASE
)


def sanitize_filename(name: str) -> str:
    """
    清理云端单个文件或文件夹名称，防止包含路径分隔符、'..' 或 Windows 保留设备名导致路径穿越或拒绝服务。
    """
    if not name:
        return "_"
    # 替换路径分隔符、空字节及 Windows 非法字符
    cleaned = re.sub(r'[/\\:\x00<>"|?*]', '_', name).strip()
    if cleaned in ('', '.', '..'):
        return f"_{cleaned}_"
    if _WIN_RESERVED_RE.match(cleaned):
        return f"_{cleaned}"
    return cleaned


def resolve_safe_subpath(base_dir: str, relative_path: str) -> str:
    """
    安全拼接本地基目录与相对路径，校验解析后的路径必须位于 base_dir 内部（防止 Path Traversal），
    并返回经过 get_safe_path 处理的路径。
    """
    if not base_dir:
        raise ValueError("base_dir 不能为空")

    clean_base = os.path.realpath(_strip_long_path_prefix(os.path.abspath(base_dir)))
    # 拒绝包含绝对盘符或根路径的 relative_path
    rel_norm = relative_path.lstrip("/\\")
    candidate = os.path.realpath(os.path.join(clean_base, rel_norm))

    try:
        common = os.path.commonpath([clean_base, candidate])
    except ValueError:
        raise ValueError(f"检测到跨盘符路径穿越风险: {relative_path}")

    if common != clean_base:
        raise ValueError(f"检测到非法路径穿越风险: {relative_path}")

    return get_safe_path(candidate)


_GDRIVE_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,256}$')


def validate_gdrive_id(item_id: str) -> str:
    """
    校验 Google Drive 文件夹/文件 ID 格式，防止命令行参数注入（如以 '-' 开头）或 API 查询注入。
    """
    if not item_id:
        return ""
    item_id = item_id.strip()
    if item_id == "root":
        return "root"
    if not _GDRIVE_ID_RE.match(item_id) or item_id.startswith("-"):
        raise ValueError(f"非法的 Google Drive ID 格式: {item_id!r}")
    return item_id


def set_secure_file_permissions(file_path: str) -> None:
    """
    将包含凭据/Token 的敏感文件权限限制为仅当前用户可读写。
    """
    if not file_path or not os.path.exists(file_path):
        return
    try:
        os.chmod(file_path, 0o600)
        if os.name == 'nt':
            username = os.environ.get("USERNAME")
            if username:
                subprocess.run(
                    ["icacls", file_path, "/inheritance:r", "/grant:r", f"{username}:(F)"],
                    capture_output=True,
                    timeout=5,
                    creationflags=0x08000000
                )
    except Exception:
        pass


def sanitize_csv_field(value):
    """
    防止 CSV 公式注入（CSV Injection）：对以 =, +, -, @, Tab, CR 开头的字符串添加单引号前缀。
    """
    if isinstance(value, str) and value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


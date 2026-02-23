"""
Rclone Wrapper - Interface to rclone.exe for stable cloud syncing
"""
import os
import subprocess
import json
import time
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass


@dataclass
class RcloneStats:
    """Rclone统计信息"""
    bytes_transferred: int
    total_bytes: int
    speed: float  # bytes/sec
    eta: int  # seconds
    errors: int
    transfers_active: int
    transfers_complete: int
    elapsed_time: float
    total_files: int = 0  # 总文件数
    transferring: List[Dict[str, str]] = None  # 当前正在传输的文件列表


class RcloneWrapper:
    """Rclone包装器 - 通过subprocess调用rclone.exe"""
    
    def __init__(self, rclone_path: str = None, config_path: str = "config/rclone.conf"):
        """
        初始化Rclone包装器
        
        Args:
            rclone_path: rclone.exe的路径 (默认自动检测)
            config_path: rclone配置文件路径
        """
        import sys
        
        # 自动确定默认文件名
        if rclone_path is None:
            if os.name == 'nt':
                default_name = "rclone.exe"
            else:
                default_name = "rclone"
            self.rclone_path = default_name
        else:
            self.rclone_path = rclone_path
            
        # 检查是否在 PyInstaller 打包环境中
        if getattr(sys, 'frozen', False):
            # 如果是打包环境，尝试在临时目录中查找
            if hasattr(sys, '_MEIPASS'):
                bundled_path = os.path.join(sys._MEIPASS, self.rclone_path)
                if os.path.exists(bundled_path):
                    self.rclone_path = bundled_path
            # 或者在可执行文件同级目录查找
            elif os.path.exists(os.path.join(os.path.dirname(sys.executable), self.rclone_path)):
                self.rclone_path = os.path.join(os.path.dirname(sys.executable), self.rclone_path)
                
        self.config_path = config_path
        self.process = None
        self.is_paused = False
        
        # 验证rclone存在
        if not os.path.exists(self.rclone_path):
            # 尝试在系统路径中查找
            import shutil
            if shutil.which(self.rclone_path):
                self.rclone_path = shutil.which(self.rclone_path)
            else:
                # 仅作为警告，不抛出异常，允许后续配置
                print(f"[Warning] Rclone未找到: {self.rclone_path}")
        
        print(f"[Rclone] 使用路径: {self.rclone_path}")
        
        # 确保配置目录存在
        os.makedirs(os.path.dirname(self.config_path) if os.path.dirname(self.config_path) else "config", exist_ok=True)
    
    def get_version(self) -> str:
        """获取rclone版本"""
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = 0x08000000 # CREATE_NO_WINDOW
                
            result = subprocess.run(
                [self.rclone_path, "version"],
                capture_output=True,
                text=True,
                timeout=5,
                **kwargs
            )
            return result.stdout.split('\n')[0] if result.returncode == 0 else "Unknown"
        except Exception as e:
            return f"Error: {e}"
    
    def setup_remote(self, remote_name: str, client_id: str, client_secret: str, token: str) -> bool:
        """
        设置Google Drive远程
        
        Args:
            remote_name: 远程名称（如 "gdrive"）
            client_id: Google OAuth Client ID
            client_secret: Google OAuth Client Secret
            token: OAuth访问令牌JSON字符串
        
        Returns:
            是否成功
        """
        try:
            # 构建rclone配置
            config_content = f"""[{remote_name}]
type = drive
client_id = {client_id}
client_secret = {client_secret}
scope = drive
token = {token}
team_drive = 
"""
            
            # 写入配置文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            print(f"[Rclone] 已创建配置: {remote_name}")
            
            # 测试连接
            return self.test_remote(remote_name)
            
        except Exception as e:
            print(f"[Rclone] 设置远程失败: {e}")
            return False
    
    def auto_setup_from_gdrive_client(self, gdrive_client, remote_name: str = "gdrive") -> bool:
        """
        自动从GDriveClient设置Rclone配置
        
        Args:
            gdrive_client: GDrive客户端实例
            remote_name: 远程名称
        
        Returns:
            是否成功
        """
        try:
            if not gdrive_client or not gdrive_client.creds:
                print("[Rclone] GDrive客户端未认证")
                return False
            
            creds = gdrive_client.creds
            
            # 构建token JSON
            import json
            token_dict = {
                "access_token": creds.token,
                "token_type": "Bearer",
                "refresh_token": creds.refresh_token,
                "expiry": creds.expiry.isoformat() if creds.expiry else None
            }
            token_json = json.dumps(token_dict)
            
            # 获取client_id和client_secret
            client_id = creds.client_id or ""
            client_secret = creds.client_secret or ""
            
            # 构建rclone配置
            config_content = f"""[{remote_name}]
type = drive
scope = drive
token = {token_json}
"""
            
            # 如果有client credentials，添加它们
            if client_id and client_secret:
                config_content += f"""client_id = {client_id}
client_secret = {client_secret}
"""
            
            # 写入配置文件
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            print(f"[Rclone] ✓ 自动生成配置: {remote_name}")
            
            # 测试连接
            return self.test_remote(remote_name)
            
        except Exception as e:
            print(f"[Rclone] 自动配置失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_user_info(self, remote_name: str = "gdrive") -> Dict[str, str]:
        """
        获取用户信息（从 token 文件中提取）
        
        Args:
            remote_name: 远程名称
        
        Returns:
            用户信息字典
        """
        try:
            # 直接读取并解析配置文件中的 token
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 提取 token JSON
                import re
                import json
                
                # 查找 token = {...}
                token_match = re.search(r'token\s*=\s*(\{[^}]+\})', content)
                if token_match:
                    try:
                        token_str = token_match.group(1)
                        token_data = json.loads(token_str)
                        
                        # 尝试提取邮箱或其他标识
                        if 'email' in token_data:
                            return {"email": token_data['email']}
                        
                        # 如果有 access_token，尝试解码（JWT）
                        access_token = token_data.get('access_token', '')
                        if access_token and '.' in access_token:
                            # 简单的 JWT 解码
                            import base64
                            try:
                                parts = access_token.split('.')
                                if len(parts) >= 2:
                                    payload = parts[1]
                                    # 添加padding
                                    payload += '=' * (4 - len(payload) % 4)
                                    decoded = base64.b64decode(payload)
                                    payload_data = json.loads(decoded)
                                    if 'email' in payload_data:
                                        return {"email": payload_data['email']}
                            except:
                                pass
                    except:
                        pass
            
            # 返回通用名称
            return {"email": "Google Drive（已连接）"}
            
        except Exception as e:
            print(f"[Rclone] 获取用户信息失败: {e}")
            return {"email": "Google Drive 用户"}
    
    def test_remote(self, remote_name: str) -> bool:
        """测试远程连接"""
        try:
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = 0x08000000 # CREATE_NO_WINDOW
                
            result = subprocess.run(
                [self.rclone_path, "lsd", f"{remote_name}:", "--config", self.config_path, "--max-depth", "1"],
                capture_output=True,
                encoding='utf-8',  # 使用 UTF-8 编码
                errors='ignore',   # 忽略编码错误
                timeout=3,  # 减少到3秒避免卡顿
                **kwargs
            )
            
            if result.returncode == 0:
                print(f"[Rclone] 远程连接成功: {remote_name}")
                return True
            else:
                print(f"[Rclone] 远程连接失败: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"[Rclone] 测试连接异常: {e}")
            return False
    
    def list_folder(self, remote_path: str, remote_name: str = "gdrive") -> List[Dict]:
        """
        列出文件夹内容
        
        Args:
            remote_path: 远程路径（文件夹ID或路径）
            remote_name: 远程名称
        
        Returns:
            文件列表
        """
        try:
            # 使用 lsjson 获取JSON格式的文件列表
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = 0x08000000 # CREATE_NO_WINDOW
                
            result = subprocess.run(
                [
                    self.rclone_path, "lsjson",
                    f"{remote_name}:{remote_path}",
                    "--config", self.config_path,
                    "--recursive",
                    "--files-only"
                ],
                capture_output=True,
                text=True,
                timeout=30,
                **kwargs
            )
            
            if result.returncode == 0:
                files = json.loads(result.stdout)
                print(f"[Rclone] 找到 {len(files)} 个文件")
                return files
            else:
                print(f"[Rclone] 列出文件失败: {result.stderr}")
                return []
                
        except Exception as e:
            print(f"[Rclone] 列出文件异常: {e}")
            return []
    
    def sync_folder(self, 
                   remote_path: str, 
                   local_path: str,
                   remote_name: str = "gdrive",
                   progress_callback: Optional[Callable[[RcloneStats], None]] = None,
                   event_callback: Optional[Callable[[str, str, str], None]] = None, # type, message, level
                   stop_flag: Optional[Callable[[], bool]] = None,
                   log_callback: Optional[Callable[[str, str], None]] = None) -> bool: # message, prefix
        """
        同步文件夹
        
        Args:
            remote_path: 远程路径（文件夹ID或路径）
            local_path: 本地路径
            remote_name: 远程名称
            progress_callback: 进度回调
            event_callback: 事件回调 (type, message, level)
            stop_flag: 停止标志
            log_callback: 日志回调 (message, level/prefix)
        
        Returns:
            是否成功
        """
        try:
            # Helper for logging
            def log(msg, prefix="ℹ"):
                if log_callback:
                    log_callback(msg, prefix)
                else:
                    print(f"[Rclone] {msg}")

            # 加载设置
            settings = getattr(self, 'settings', None)
            if not settings:
                # 尝试从文件加载
                settings_file = "config/app_settings.json"
                if os.path.exists(settings_file):
                    import json
                    with open(settings_file, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
            
            # 默认设置
            rclone_settings = settings.get('rclone', {}) if settings else {}
            download_settings = settings.get('download', {}) if settings else {}
            
            checkers = rclone_settings.get('checkers', 8)
            transfers = rclone_settings.get('transfers', 4)
            chunk_size = rclone_settings.get('chunk_size', 64)
            retries = rclone_settings.get('retries', 10)
            low_level_retries = rclone_settings.get('low_level_retries', 10)
            
            # 构建rclone命令
            cmd = [
                self.rclone_path, "copy",
                f"{remote_name}:",  # 使用根目录，通过 --drive-root-folder-id 指定文件夹
                local_path,
                "--config", self.config_path,
                # "--drive-root-folder-id", remote_path,  # 移动到下面判断
                "--progress",
                "--stats", "1s",
                "--retries", str(retries),
                "--low-level-retries", str(low_level_retries),
                "--checkers", str(checkers),
                "--transfers", str(transfers),
                "--drive-chunk-size", f"{chunk_size}M",
                "-v",  # 详细输出
                "--use-server-modtime", # 使用服务器修改时间
            ]
            
            # 如果指定了特定文件夹（且不是根目录），则添加过滤
            if remote_path and remote_path != "root":
                cmd.extend(["--drive-root-folder-id", remote_path])
            
            # 带宽限制
            if download_settings.get('bwlimit_enabled', False):
                bwlimit = download_settings.get('bwlimit', 0)
                if bwlimit > 0:
                    cmd.extend(["--bwlimit", f"{bwlimit}M"])
            
            # 删除空目录 (rclone copy 不支持此参数，仅 move/sync 支持，且 copy 不应修改源文件)
            # if download_settings.get('delete_empty_dirs', False):
            #     cmd.append("--delete-empty-src-dirs")
            
            log(f"执行命令: {' '.join(cmd)}", "🚀")
            
            # 启动进程
            kwargs = {}
            if os.name == 'nt':
                kwargs['creationflags'] = 0x08000000 # CREATE_NO_WINDOW

            log("正在启动 Rclone 进程...", "⚙")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding='utf-8',  # 强制使用 UTF-8
                errors='ignore',   # 忽略无法解码的字符
                bufsize=1,
                **kwargs
            )
            log("Rclone 进程已启动", "✓")
            
            # 读取输出
            current_stats = {
                'bytes_transferred': 0,
                'total_bytes': 0,
                'speed': 0,
                'eta': 0,
                'errors': 0,
                'transfers_active': 0,
                'transfers_complete': 0,
                'elapsed_time': 0,
                'transferring': []
            }
            
            # 状态标志
            in_transferring_section = False
            
            for line in self.process.stdout:
                # 检查停止标志
                if stop_flag and stop_flag():
                    log("收到停止信号", "⏹")
                    self.stop()
                    return False
                
                line = line.strip()
                if not line:
                    continue
                
                # 打印原始日志（用于调试）- 用户要求打印所有环节
                log(f"[RAW] {line}", "📝")
                
                # --- 解析事件日志 ---
                # INFO : filename: Copied (new)
                # INFO : filename: Copied (replaced)
                # INFO : filename: Unchanged skipping
                # ERROR : filename: Failed to copy: ...
                # --- 解析事件日志 (更宽容的解析) ---
                # INFO : filename: Copied (new)
                # ERROR : filename: Failed to copy: ...
                # 2024/02/11 ... : filename: Copied
                
                try:
                    # 成功 (Copied)
                    if ": Copied" in line:
                        # 尝试提取文件名
                        # 格式通常是: ... : filename: Copied ...
                        # 我们找 ": Copied" 之前的部分，再找上一个冒号
                        
                        # 简单的切分策略：
                        # 1. split by ": Copied" -> [prefix_with_filename, suffix]
                        # 2. prefix_with_filename 如 "2024/.. INFO : my_file.txt"
                        # 3. taking the last part after " : " might work
                        
                        parts = line.split(": Copied")
                        prefix = parts[0]
                        extra_info = parts[1].strip() if len(parts) > 1 else ""
                        
                        # 寻找文件名起始位置
                        # Rclone 日志通常有 " : " 分隔前缀和内容
                        last_colon_index = prefix.rfind(" : ")
                        if last_colon_index != -1:
                             file_name = prefix[last_colon_index + 3:].strip()
                             
                             if event_callback:
                                event_callback("success", f"已完成: {file_name} {extra_info}", "INFO")
                        else:
                             # 也许没有前缀？直接是文件名？不太可能，但兜底
                             # 或者格式是 "filename: Copied"
                             file_name = prefix.strip()
                             if event_callback:
                                event_callback("success", f"已完成: {file_name} {extra_info}", "INFO")

                    # 跳过 (Unchanged)
                    elif ": Unchanged skipping" in line:
                        if event_callback:
                             # 提取文件名逻辑同上
                             parts = line.split(": Unchanged skipping")
                             prefix = parts[0]
                             last_colon_index = prefix.rfind(" : ")
                             if last_colon_index != -1:
                                 file_name = prefix[last_colon_index + 3:].strip()
                             else:
                                 file_name = prefix.strip()
                             # 用户要求打印所有状态? "日志就是打印所有的处理状态"
                             # 既然这样，跳过也打印一下吧，用灰色
                             event_callback("info", f"跳过: {file_name}", "INFO")
                    
                    # 错误 (ERROR)
                    elif "ERROR :" in line or "Failed to copy" in line:
                         # 尝试提取错误信息
                         error_msg = line
                         file_name = "Unknown"
                         
                         if "Failed to copy:" in line:
                             parts = line.split("Failed to copy:")
                             error_detail = parts[1].strip()
                             
                             # 尝试找文件名
                             prefix = parts[0]
                             # remove "ERROR :" if present
                             prefix = prefix.replace("ERROR :", "").strip()
                             # remove timestamp/level prefix if present
                             last_colon_index = prefix.rfind(" : ")
                             if last_colon_index != -1:
                                 file_name = prefix[last_colon_index + 3:].strip()
                             elif prefix.endswith(":"):
                                 file_name = prefix[:-1].strip()
                             else:
                                 file_name = prefix
                                 
                             error_msg = f"{file_name} -> {error_detail}"
                         
                         if event_callback:
                            event_callback("error", f"失败: {error_msg}", "ERROR")

                except Exception as e:
                    # print(f"Log parse error: {e}")
                    pass

                # 解析传输部分标志
                if line.startswith("Transferring:"):
                    in_transferring_section = True
                    current_stats['transferring'] = [] # 清空列表，准备接收新数据
                    continue
                elif in_transferring_section and not line.startswith("*"):
                     # 如果进入了传输部分，但行不是以 * 开头，说明传输部分结束了
                     pass

                # 解析详细传输文件行
                # 格式1: * filename: 10% / 50MB, 1.2MB/s, 10s
                # 格式2: * filename: transferring
                # 格式3: * filename: 0% / 10MB, 0/s, -
                if in_transferring_section and line.startswith("*"):
                    try:
                        # 移除开头的 "* "
                        file_line = line[2:].strip()
                        
                        # Rclone 输出的文件名可能包含冒号，但进度信息部分通常在最后
                        # 典型的结尾是: x% / xMB, xMB/s, xs
                        # 或者: transferring
                        
                        file_name = ""
                        percentage = "0%"
                        size = "-"
                        speed = "-"
                        eta = "-"
                        status = "等待中" # 默认为等待/传输中
                        
                        # 检查是否只有 "transferring"
                        if file_line.endswith(": transferring"):
                            file_name = file_line[:-14].strip()
                            status = "准备传输"
                        else:
                            # 尝试查找最后一个冒号，但这不可靠，因为文件名可能有冒号
                            # 更好的方法是看行尾模式
                            # 典型的进度部分包含逗号分隔
                            
                            last_colon = file_line.rfind(':')
                            if last_colon != -1:
                                potential_progress = file_line[last_colon+1:].strip()
                                # 检查这一段是否像进度信息 (包含 %, /, ,)
                                if "%" in potential_progress or "transferring" in potential_progress:
                                    file_name = file_line[:last_colon].strip()
                                    progress_info = potential_progress
                                    
                                    if "transferring" in progress_info:
                                        status = "准备传输"
                                    else:
                                        status = "传输中"
                                        # 解析进度信息
                                        # 可能格式 1: 10% / 50MB, 1.2MB/s, 10s
                                        # 可能格式 2: 50MB / 100MB, 10%, 1.2MB/s, 10s
                                        parts = [p.strip() for p in progress_info.split(',')]
                                        
                                        if len(parts) >= 1:
                                            part0 = parts[0]
                                            # 检查第一部分是否包含 %
                                            if '%' in part0 and '/' in part0:
                                                # 格式 1: 10% / 50MB
                                                prog_parts = part0.split('/')
                                                if len(prog_parts) >= 1:
                                                    percentage = prog_parts[0].strip()
                                                if len(prog_parts) >= 2:
                                                    size = prog_parts[1].strip()
                                                
                                                if len(parts) >= 2: speed = parts[1].strip()
                                                if len(parts) >= 3: eta = parts[2].strip()
                                            
                                            elif '/' in part0:
                                                # 格式 2: 50MB / 100MB
                                                prog_parts = part0.split('/')
                                                if len(prog_parts) >= 2:
                                                    size = prog_parts[1].strip() #取总大小
                                                
                                                # 找百分比
                                                if len(parts) >= 2 and '%' in parts[1]:
                                                    percentage = parts[1].strip()
                                                    if len(parts) >= 3: speed = parts[2].strip()
                                                    if len(parts) >= 4: eta = parts[3].strip()
                                                else:
                                                    # 只有大小?
                                                    pass
                                            else:
                                                # 简单的进度?
                                                pass

                                else:
                                    # 冒号可能在文件名里，且这行可能不包含标准进度？
                                    # 暂时假设整行是文件名，或者忽略
                                    continue
                            else:
                                continue

                        current_stats['transferring'].append({
                            'name': file_name,
                            'percentage': percentage,
                            'size': size,
                            'speed': speed,
                            'eta': eta,
                            'status': status
                        })
                    except Exception:
                        pass
                    continue # 继续处理下一行

                # 解析全局统计信息 (Bytes)
                if "Transferred:" in line and "100%" not in line and "%" in line:
                    # Rclone 有两行 Transferred
                    # 1. Transferred: 57.6 MiB / 57.6 MiB, 100%, 0 B/s, ETA - (Bytes)
                    # 2. Transferred: 1 / 1, 100% (Files)
                    
                    # 尝试匹配 Bytes 行 (带单位 或 纯数字带小数点)
                    # 注意：有时候 bytes 行也可能没有小数点 if pure bytes, but usually rclone uses units.
                    # 区分特征：Bytes 行通常有 speed (x B/s) 和 ETA
                    
                    if "ETA" in line:
                         # 重置传输列表标志，因为遇到新的统计块了
                        in_transferring_section = False
                        
                        try:
                            import re
                            # 匹配: 1.2 M / 2.4 G
                            # 或者: 100 / 200 (bytes without units? rare but possible)
                            # 我们可以依靠 ETA 来确信这是 Bytes/Speed 行
                            
                            # 提取传输量和总量的通用匹配
                            # 寻找 / 分隔的两个值，后面跟一个百分比
                            # 例子: 57.6 MiB / 57.6 MiB, 100%
                            parts = line.split(',')
                            if len(parts) >= 1 and '/' in parts[0]:
                                counts_part = parts[0].replace("Transferred:", "").strip()
                                transferred_str, total_str = counts_part.split('/')
                                
                                # 解析带单位的数值函数
                                def parse_rclone_size(s):
                                    s = s.strip()
                                    match = re.match(r'(\d+\.?\d*)\s*(\w+)?', s)
                                    if match:
                                        val = float(match.group(1))
                                        unit = match.group(2)
                                        if unit:
                                            unit = unit.strip().upper()
                                            if 'K' in unit: val *= 1024
                                            elif 'M' in unit: val *= 1024 * 1024
                                            elif 'G' in unit: val *= 1024 * 1024 * 1024
                                            elif 'T' in unit: val *= 1024 * 1024 * 1024 * 1024
                                            elif 'P' in unit: val *= 1024 * 1024 * 1024 * 1024 * 1024
                                        return int(val)
                                    return 0

                                current_stats['bytes_transferred'] = parse_rclone_size(transferred_str)
                                current_stats['total_bytes'] = parse_rclone_size(total_str)
                            
                            # 提取速度
                            # ... 100%, 10.000 MiB/s, ETA ...
                            speed_match = re.search(r'(\d+\.?\d*)\s*(\w+)/s', line)
                            if speed_match:
                                current_stats['speed'] = parse_rclone_size(f"{speed_match.group(1)} {speed_match.group(2)}")
                            
                            # 提取 ETA
                            eta_match = re.search(r'ETA\s+([\w\s]+)', line)
                            if eta_match:
                                eta_str = eta_match.group(1).strip()
                                # 简单解析 ETA (0s, 1m20s, -)
                                current_stats['eta'] = 0 # 简化，UI可以处理字符串或这里解析成秒
                                if 's' in eta_str or 'm' in eta_str or 'h' in eta_str:
                                    # 这里的 ETA 解析比较复杂，暂时先存 0，UI 如果直接用字符串解析更好，但 RcloneStats 定义是 float
                                    # 尝试解析秒数
                                    total_seconds = 0
                                    try:
                                        # 1h2m3s
                                        t_parts = re.findall(r'(\d+)([hms])', eta_str)
                                        for val, unit in t_parts:
                                            if unit == 'h': total_seconds += int(val) * 3600
                                            elif unit == 'm': total_seconds += int(val) * 60
                                            elif unit == 's': total_seconds += int(val)
                                        current_stats['eta'] = total_seconds
                                    except:
                                        pass

                        except Exception:
                            pass
                    
                    else:
                        # 可能是 Files 行: Transferred: 5 / 10, 50%
                        # 特征：没有 ETA，没有速度
                         try:
                            import re
                            # 匹配: 5 / 10, 50%
                            parts = line.split(',')
                            if len(parts) >= 1 and '/' in parts[0]:
                                counts_part = parts[0].replace("Transferred:", "").strip()
                                finished_str, total_str = counts_part.split('/')
                                current_stats['transfers_complete'] = int(finished_str.strip())
                                # 这里 total_files 暂时没地方存，复用 transfers_active 或者加一个字段？
                                # RcloneStats definition: transfers_complete=0, transfers_active (int)
                                # 我们可以把 Total Files 放在 transfers_active 吗？不，transfers_active 是当前并发数
                                # 我们需要修改 RcloneStats 或 借用 total_bytes (不行)
                                # 我们可以把 total files 存在 stats 对象的一个新属性里，但 dataclass 是固定的。
                                # 让我们看看 RcloneStats 定义。
                                # 它在 core/rclone_wrapper.py 顶部。
                                # 我们应该修改 RcloneStats 定义来包含 total_files。
                                # 但现在没法改定义 (在上面)，我们先用 attributes 动态加？不，dataclass 不行。
                                # 此时，我们可以把 total_files 临时放到 transfers_active 传出去？
                                # 或者：transfers_complete 是已完成数。
                                # 我们可以添加 logic 来计算 errors。
                                pass # 先不改 RcloneStats 结构，稍后看是否需要
                                
                                # 既然不能改 RcloneStats 结构（除非我多做一个 edit call），
                                # 我将把 (completed, total) tuple 放入 transfers_active (hack) 或者
                                # 只能修改 RcloneStats 定义。为了稳健，还是修改 RcloneStats 定义吧。
                                # 但现在我正在 replace_file_content 这一大块。
                                # 我将在下面的代码中尝试把 stats 作为一个字典传出去 或者 修改 RcloneStats。
                                # 既然是 dataclass，我必须修改定义。
                                # 让我先完成这个 block，然后如果需要，我再去修改 RcloneStats 定义。
                                # 实际上，我可以利用 transfers_active 来传递 total_files? 
                                # 不，active = 正在传输的。
                                # 
                                # Wait, I can send a custom dict or update the parsed stats logic.
                                # Let's parse 'total_files' here into a variable.
                                current_stats['total_files'] = int(total_str.strip())
                                # current_stats 字典有 'transfers_complete'
                                
                         except Exception:
                            pass
                
                # 解析 Errors
                if line.startswith("Errors:"):
                    try:
                        # Errors: 0
                        errors_str = line.replace("Errors:", "").strip()
                        current_stats['errors'] = int(errors_str)
                    except:
                        pass
                
                # 发送进度
                if progress_callback and (("Transferred:" in line) or (line.startswith("*") and in_transferring_section)):
                    # 构造 stats 对象
                    # 注意：如果 RcloneStats 没有 total_files 字段，我们需要加一下。
                    # 为了安全，我稍后会去增加这个字段。
                    # 现在先构造基本对象
                    
                    # 动态添加 extra 属性?
                    stats = RcloneStats(
                        bytes_transferred=current_stats['bytes_transferred'],
                        total_bytes=current_stats['total_bytes'],
                        speed=current_stats['speed'],
                        eta=current_stats['eta'],
                        errors=current_stats['errors'],
                        transfers_active=len(current_stats['transferring']),
                        transfers_complete=current_stats['transfers_complete'],
                        elapsed_time=current_stats['elapsed_time'],
                        transferring=list(current_stats['transferring'])
                    )
                    # Hack: 动态添加 total_files 属性
                    stats.total_files = current_stats.get('total_files', 0)
                    
                    progress_callback(stats)
            
            # 等待进程结束
            return_code = self.process.wait()
            self.process = None
            
            if return_code == 0:
                log("同步完成", "✓")
                return True
            else:
                log(f"同步失败，退出代码: {return_code}", "✗")
                return False
                
        except Exception as e:
            if 'log' in locals():
                log(f"同步异常: {e}", "✗")
            else:
                print(f"[Rclone] Exception: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def stop(self):
        """停止当前操作"""
        if self.process and self.process.poll() is None:
            print("[Rclone] 正在停止进程...")
            self.process.terminate()
            
            # 等待最多3秒
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                print("[Rclone] 强制结束进程")
                self.process.kill()
                self.process.wait()
            
            self.process = None
            print("[Rclone] 进程已停止")

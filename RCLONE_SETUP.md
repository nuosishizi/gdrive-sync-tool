# Rclone 配置指南

## 快速配置（5分钟）

### 1. 运行 Rclone 配置向导

打开命令提示符（CMD），进入 rclone 目录：

```bash
cd C:\path\to\rclone
rclone.exe config
```

### 2. 创建新的 Google Drive 远程

按照以下步骤操作：

1. **输入 `n`** (New remote)
2. **远程名称：** 输入 `gdrive` （必须是这个名字）
3. **Storage 类型：** 选择 `drive` (Google Drive)
4. **Client ID：** 直接按回车（使用默认）
5. **Client Secret：** 直接按回车（使用默认）
6. **Scope：** 选择 `1` (Full access)
7. **Root folder ID：** 直接按回车
8. **Service Account：** 直接按回车
9. **Auto config：** 输入 `y` (Yes)
   - 会自动打开浏览器
   - 登录你的 Google 账号
   - 授权 Rclone
10. **Configure as team drive：** 输入 `n` (No)
11. **确认配置：** 输入 `y` (Yes)
12. **退出：** 输入 `q` (Quit)

### 3. 查看配置文件位置

```bash
rclone.exe config file
```

会显示配置文件路径，例如：
```
Configuration file is stored at:
C:\Users\<YourUsername>\AppData\Roaming\rclone\rclone.conf
```

### 4. 复制配置文件到应用目录

找到上面显示的 `rclone.conf` 文件，复制到：
```
C:\path\to\gdrive-sync-tool\config\rclone.conf
```

或者直接在 CMD 运行：
```bash
copy %APPDATA%\rclone\rclone.conf gdrive_sync\config\rclone.conf
```

### 5. 测试配置

测试 Rclone 是否能连接：
```bash
rclone.exe lsd gdrive: --config gdrive_sync\config\rclone.conf
```

如果看到你的 Google Drive 文件夹列表，说明配置成功！

## 现在可以使用应用了！

配置完成后：
1. 重启应用 `python gdrive_sync\main.py`
2. 选择 Google Drive 文件夹 ID
3. 选择本地文件夹
4. 点击"开始同步"

✅ **不再有 SSL 错误！**
✅ **稳定可靠的下载！**
✅ **自动断点续传！**

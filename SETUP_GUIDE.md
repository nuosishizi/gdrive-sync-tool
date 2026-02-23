# Google Drive 同步工具 - 快速开始指南

## 第一步：安装 Python

确保已安装 Python 3.8 或更高版本。

检查 Python 版本：
```bash
python --version
```

## 第二步：安装依赖

打开命令提示符（CMD）或 PowerShell，进入项目目录：

```bash
cd C:\path\to\gdrive-sync-tool
pip install -r requirements.txt
```

> **注意：** 该工具依赖 `rclone` 执行下载。程序**会在首次执行时自动为您下载对应平台（Windows/macOS/Linux）的版本**。如果您已经在系统 PATH 配置过 `rclone` 或者将可执行文件放置在了项目根目录，程序将跳过下载并直接使用本地。

## 第三步：配置 Google Drive API

### 3.1 创建 Google Cloud 项目

1. 访问 https://console.cloud.google.com/
2. 点击"选择项目" → "新建项目"
3. 输入项目名称（如：GDrive Sync），点击"创建"

### 3.2 启用 Google Drive API

1. 在左侧菜单选择"API 和服务" → "库"
2. 搜索 "Google Drive API"
3. 点击进入，点击"启用"

### 3.3 创建 OAuth 2.0 凭据

1. 左侧菜单选择"API 和服务" → "凭据"
2. 点击"创建凭据" → "OAuth 客户端 ID"
3. 如果提示配置同意屏幕：
   - 选择"外部"，点击"创建"
   - 填写应用名称（如：GDrive Sync）
   - 用户支持电子邮件：填写您的 Gmail
   - 开发者联系电子邮件：填写您的 Gmail
   - 点击"保存并继续"
   - 作用域页面直接点击"保存并继续"
   - 测试用户页面点击"添加用户"，输入您的 Gmail
   - 点击"保存并继续"
4. 返回"创建 OAuth 客户端 ID"：
   - 应用类型选择"桌面应用"
   - 名称填写"GDrive Sync Client"
   - 点击"创建"
5. 下载生成的 JSON 文件
6. 将文件重命名为 `credentials.json`
7. 放入项目的 `config/` 文件夹中

## 第四步：运行应用

```bash
python main.py
```

## 第五步：首次授权

1. 应用启动后，点击"授权 Google 账号"
2. 浏览器会自动打开 Google 授权页面
3. 选择您的 Google 账号
4. 可能会提示"Google 尚未验证此应用"：
   - 点击左侧"高级"
   - 点击"前往 GDrive Sync（不安全）"
5. 勾选"查看和下载您的所有 Google 云端硬盘文件"
6. 点击"继续"
7. 授权成功后，应用会显示"已连接: your@gmail.com"

## 第六步：开始同步

### 6.1 获取 Google Drive 文件夹 ID

1. 打开 https://drive.google.com/
2. 进入您要下载的文件夹
3. 查看浏览器地址栏，复制 `folders/` 后面的字符串

例如：
```
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz
                                        ^^^^^^^^^^^^^^^^^^^^^^^^
                                        这是文件夹 ID
```

### 6.2 配置同步任务

1. 在"Google Drive 源文件夹"中粘贴文件夹 ID
2. 点击"浏览本地..."选择下载到的本地文件夹
3. 点击"▶ 开始同步"

## 常见问题

### 问题 1：找不到 credentials.json
**解决**：确保文件放在 `gdrive_sync/config/credentials.json`

### 问题 2：授权时提示"访问被阻止"
**解决**：
1. 点击"高级"
2. 点击"前往应用（不安全）"
3. 这是因为应用未经 Google 验证，但您自己的项目是安全的

### 问题 3：pip install 失败
**解决**：尝试使用国内镜像源：
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 问题 4：下载速度慢
**解决**：
1. 点击"⚙ 设置"
2. 增加并发线程数（如：5-10）

## 高级功能

### 过滤规则
在设置中可以配置：
- **文件类型**：只下载特定类型（如 .jpg, .mp4）
- **文件大小**：设置最小/最大大小限制
- **文件名**：排除特定文件

### 任务管理
保存多个同步配置，快速切换：
1. 点击"任务管理"
2. 点击"+ 新建"
3. 配置任务名称和路径
4. 保存后可在下拉菜单切换

### 定时同步
设置自动同步计划，无需手动操作。

## 打包为 EXE（可选）

生成独立的 .exe（Windows）或 .app（macOS） 文件：

```bash
pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed --name="GDriveSync" main.py
```

生成的发行版在 `dist/` 文件夹中。程序发行版不包含 `rclone`，首次运行时会根据不同平台**自动下载它**。

## 支持

如有问题，请检查日志区域的错误信息，或导出日志 CSV 文件进行分析。

# Google Drive 下载同步工具

一个功能强大的 Google Drive 下载同步工具，支持增量同步、断点续传、文件校验等功能。

## 功能特性

✅ **Google OAuth2 授权** - 安全的账号授权  
✅ **增量同步** - 只下载新增/修改的文件  
✅ **断点续传** - 大文件分块下载，支持中断恢复  
✅ **文件校验** - MD5 校验确保文件完整性  
✅ **错误重试** - 自动重试失败的下载  
✅ **多线程下载** - 提高下载速度  
✅ **任务管理** - 保存多个同步任务配置  
✅ **过滤规则** - 按文件类型/大小过滤  
✅ **带宽限制** - 控制下载速度  
✅ **详细日志** - 记录所有操作

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置 Google Drive API

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 启用 **Google Drive API**
4. 创建 **OAuth 2.0 客户端 ID**（应用类型选择"桌面应用"）
5. 下载 JSON 凭据文件
6. 将文件重命名为 `credentials.json` 并放入 `config/` 目录

## 使用方法

### 启动应用

```bash
python main.py
```

### 首次使用

1. 点击"授权 Google 账号"按钮
2. 浏览器会自动打开授权页面
3. 登录并授权应用访问 Google Drive
4. 授权成功后返回应用

### 配置同步任务

1. 输入 Google Drive 文件夹 ID
   - 打开 Google Drive 网页版
   - 进入要同步的文件夹
   - 从地址栏复制文件夹 ID（`folders/` 后面的部分）
   
2. 选择本地目标文件夹

3. 点击"开始同步"

### 高级功能

- **预览**: 查看将要下载的文件列表
- **任务管理**: 保存和切换多个同步配置
- **设置**: 配置过滤规则、带宽限制、线程数等
- **导出日志**: 导出同步日志为 CSV 文件

## 项目结构

```
gdrive_sync/
├── main.py              # 应用入口
├── requirements.txt     # 依赖包
├── config/             # 配置文件（OAuth 凭据）
├── ui/                 # PyQt6 界面
├── core/               # 核心功能
│   ├── gdrive_client.py   # Google Drive API
│   ├── sync_engine.py     # 同步引擎
│   └── downloader.py      # 下载器
├── database/           # SQLite 数据库
└── utils/              # 工具函数
```

## 常见问题

### Q: 如何获取文件夹 ID？
A: 在 Google Drive 网页版打开文件夹，地址栏中 `folders/` 后面的字符串就是文件夹 ID。

### Q: 下载中断后如何继续？
A: 应用会自动记录下载进度，再次启动同步即可从断点继续。

### Q: 如何过滤特定文件？
A: 点击"设置"按钮，在过滤规则中配置文件类型、大小等条件。

### Q: 出现授权错误怎么办？
A: 点击"重新授权"按钮，重新完成授权流程。

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

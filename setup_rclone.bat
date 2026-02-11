@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  Rclone Google Drive 配置向导
echo ========================================
echo.

REM 检查是否已有配置
if exist "%APPDATA%\rclone\rclone.conf" (
    echo [发现] 已有 Rclone 配置文件
    echo 位置: %APPDATA%\rclone\rclone.conf
    echo.
    choice /C YN /M "是否要复制到应用目录？"
    if errorlevel 2 goto END
    if errorlevel 1 goto COPY_CONFIG
)

echo [提示] 准备运行 Rclone 配置向导...
echo.
echo 配置步骤：
echo 1. 输入 n (新建远程)
echo 2. 名称输入: gdrive
echo 3. 类型选择: drive (Google Drive)
echo 4. Client ID/Secret: 直接按回车
echo 5. Scope: 选择 1 (Full access)
echo 6. Auto config: 输入 y (会打开浏览器登录)
echo 7. Team drive: 输入 n
echo 8. 确认: 输入 y
echo 9. 退出: 输入 q
echo.
pause

REM 运行 rclone config
..\rclone.exe config

:COPY_CONFIG
echo.
echo [复制] 正在复制配置文件...
if not exist "config" mkdir config
copy /Y "%APPDATA%\rclone\rclone.conf" "config\rclone.conf"

if errorlevel 1 (
    echo [错误] 复制失败！
    pause
    exit /b 1
)

echo [成功] 配置文件已复制到: %cd%\config\rclone.conf
echo.

REM 测试配置
echo [测试] 正在测试 Rclone 连接...
..\rclone.exe lsd gdrive: --config config\rclone.conf --max-depth 1

if errorlevel 1 (
    echo.
    echo [警告] 连接测试失败，请检查配置
) else (
    echo.
    echo [成功] Rclone 配置完成！
    echo.
    echo 现在可以运行应用: python main.py
)

:END
echo.
pause

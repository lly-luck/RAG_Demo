智慧问答系统 · 便携版
====================

一、启动
1. 将整个 RAGDemo-portable 文件夹解压/复制到任意目录（不要只拷 启动.bat）。
   Windows 11 资源管理器可直接解压 .7z；Windows 10 请先安装 7-Zip。
2. 双击 启动.bat（或 launcher\launcher.exe）。
3. 首次启动会自动解压 Python 运行时（约 1–3 分钟），然后加载本地模型（约 15–40 秒），
   就绪后自动打开浏览器。请耐心等待启动器窗口里的进度。
4. 首次使用请在页面右上角“设置”中填写：
   - Base URL（默认 https://api.deepseek.com）
   - 模型名（默认 deepseek-chat）
   - API Key（你自己的 Key）
   点击“测试连接”，成功后保存。Key 只保存在本机，不会上传。

二、数据位置
- 默认：%LOCALAPPDATA%\RAGDemo
  - config.ini：大模型设置
  - data\app.db：SQLite（FAQ + 会话历史）
  - data\vector_db：Chroma 知识库
  - logs：应用/服务日志
  - runtime：运行时缓存（首次解压）
- 完全绿色模式：在便携目录放一个空的 portable.txt，配置/数据/运行时写到
  便携目录下的 .ragdemo（要求目录可写）。

三、移动与复制
- 首次运行后，整个便携文件夹可以复制/移动到其他路径，运行时不依赖原路径。
- 如果删除了 %LOCALAPPDATA%\RAGDemo，下次启动会重新解压运行时、重新初始化数据。

四、卸载
- 删除便携文件夹即完成卸载。
- 如需清理用户数据，删除 %LOCALAPPDATA%\RAGDemo（或便携目录下的 .ragdemo）。

五、体积与环境要求
- 便携目录约 5.5GB（代码/模型约 3.7GB + runtime.zip 约 1.9GB）；分发的 .7z 约 2.9GB。
- 首次运行后运行时缓存约 2.1GB，最终磁盘占用约 7.7GB。
- 建议 Windows 10/11 64 位、16GB 内存、SSD；.7z 小于 4GB，FAT32 U 盘也可存放，
  但解压/运行建议放在 NTFS/exFAT 本地盘。
- 首次启动和每次启动加载模型需要一定时间，属于正常现象。

六、常见问题
- 浏览器没有自动打开：在启动器窗口点“打开页面”，或手动访问窗口里显示的地址。
- 端口被占用：启动器会自动换一个空闲端口。
- 杀毒软件提示：launcher\launcher.exe 未签名，可能被 SmartScreen/杀软误报，可添加信任。
- 没有网络：FAQ 和问候语仍可用；RAG 回答需要大模型 API，请检查网络/Key。
- 启动失败：点“打开日志”，查看 logs\server.err.log 和 logs\launcher.log。
- 检索效果不佳：确认 data\vector_db 已随包提供；首次启动会自动复制种子。

七、开发/更新
- 修改代码后重新运行 packaging\build.py 生成新的便携包。
- 版本号见 VERSION 文件；运行时缓存按版本隔离，升级不影响旧版本。

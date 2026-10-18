# 参与维护

提交问题时附上版本、操作系统、Python 版本和去除个人信息后的错误信息；不要附学号密码、邮箱授权码、Cookie、实际配置或完整 HAR 文件。

维护代码请以 `windows/` 或 `linux/` 为入口；`archive/` 是原始存档，避免直接改动。新功能与修复使用真实提交时间，并在 `CHANGELOG.md` 增加说明，不沿用历史回填日期。依赖变化需同步运行说明与离线检查。

提交前可运行 `python -m compileall -q windows linux archive`。该检查仅验证 Python 语法；涉及学校接口的兼容性需要另行通过本人有权使用的账号验证。

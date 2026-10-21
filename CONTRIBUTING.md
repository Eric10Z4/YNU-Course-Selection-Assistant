# 参与维护

先阅读 [项目规则](AGENTS.md)、[开发流程](docs/DEVELOPMENT.md) 和 [平台计划](docs/ROADMAP.md)。各平台结果按 [验收矩阵](docs/TEST_MATRIX.md) 记录，不能把语法通过或构建成功当成全部业务验收通过。

提交问题时附上版本、操作系统、Python 版本和去除个人信息后的错误信息；不要附学号密码、邮箱授权码、Cookie、实际配置或完整 HAR 文件。

维护代码请以 `windows/` 或 `linux/` 为入口；`archive/` 是原始存档，避免直接改动。新功能与修复使用真实提交时间，并在 `CHANGELOG.md` 增加说明，不沿用历史回填日期。依赖变化需同步运行说明与离线检查。

提交前可运行 `python -m compileall -q windows linux archive`。该检查仅验证 Python 语法；涉及学校接口的兼容性需要另行通过本人有权使用的账号验证。

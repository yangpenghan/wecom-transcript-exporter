# 参与开发

先阅读 [架构与限制](docs/architecture.md)。请保持原文逐字保留、后台运行、用户明确同意本地读取，以及不覆盖已有导出文件的行为。

## 验证

在 Windows 上运行 `Setup.cmd`，然后：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

浏览器测试使用合成数据，参见 README。修改界面时请检查中文提示、窄屏布局和失败后的恢复流程。修改读取器时使用合成数据库或字节样例；不要提交真实录音数据。

提交前运行 `git diff --cached --check`，检查暂存区文件及差异。不要强制加入 `.gitignore` 中的数据库、密钥、导出文件或开发缓存。若 Git 提交邮箱属于私人邮箱，请在仓库本地配置 GitHub 提供的 noreply 地址。

新增依赖需保留许可证及来源说明。第三方资源继续适用各自许可证；项目标志不代表对衍生项目的背书。

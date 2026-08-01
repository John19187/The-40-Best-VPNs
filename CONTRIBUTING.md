# 贡献指南

感谢帮助维护服务商状态、链接与价格。本项目欢迎真实、有来源的
修正；不接受为了增加贡献数量而拆分的空改动，也不接受广告文案。

## 可以贡献什么

- 修正失效链接、停运状态或服务商名称。
- 更新有公开来源的套餐、协议和客户端信息。
- 改进数据校验、链接检查脚本和维护文档。

请勿提交账号密码、订阅地址、节点凭据、个人 IP、付款记录或其他敏感信息。

## 修改流程

1. Fork 仓库并创建独立分支。
2. 服务商基本信息修改在 `data/providers.yml` 中完成。
3. 如果 README 中对应文字已经过期，同时做最小范围修正。
4. 在仓库根目录运行：

   ```bash
   python -m pip install -r requirements.txt
   python scripts/validate_data.py
   python scripts/check_links.py
   ```

5. 提交 Pull Request，说明修改原因和信息来源。

## 数据要求

- `source_heading` 必须与 README 中的二级标题完全一致。
- 暂无网址的条目使用 `null`，确认后再补充。
- 链接检查结果用于持续维护和发现需要更新的入口。

## Pull Request 检查清单

- [ ] 修改只包含一个清晰目的。
- [ ] 所有事实都有公开来源或可复现证据。
- [ ] 没有提交凭据、订阅地址或个人信息。
- [ ] `python scripts/validate_data.py` 已通过。
- [ ] README 与结构化数据不存在明显冲突。

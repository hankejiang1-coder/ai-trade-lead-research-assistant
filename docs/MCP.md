# MCP 接入

MCP供兼容客户端调用研究功能，本地网页是另一入口。当前为**本地stdio**，不是可粘贴到任意云平台的远程地址。

先用网页启动脚本创建项目环境，并把自己的密钥保存到系统凭据库。仅在网页内存配置的密钥不会传给另一个MCP进程。

Mac/Linux示例，请替换为实际绝对路径：

```json
{
  "mcpServers": {
    "trade-research": {
      "command": "/ABSOLUTE/PATH/ai-trade-lead-research-assistant/.venv/bin/python",
      "args": ["/ABSOLUTE/PATH/ai-trade-lead-research-assistant/app.py", "--mcp"]
    }
  }
}
```

Windows使用项目`.venv\\Scripts\\python.exe`，客户端实际注册格式可能不同。不要把密钥写进共享配置。

工具`research_company`支持公司名称、国家、官网、我方产品及已确认的名片文字；`refresh_evidence=true`可强制检索并增加费用。名片照片上传/识别目前在网页入口，不能称为MCP图片接口。

已用官方Python MCP SDK测试握手、工具发现、无效输入及一次ICL研究调用。具体Codex、DeepSeek Harness及其他客户端的注册和端到端体验仍需分别验证。

普通使用者无需安装测试SDK。开发者可在独立环境安装`mcp`后运行`check_mcp_client.py`做无付费协议检查。`--live-icl`仅供开发回归，要求已有未过期资料缓存且会产生一次模型生成费；仓库不含此缓存。

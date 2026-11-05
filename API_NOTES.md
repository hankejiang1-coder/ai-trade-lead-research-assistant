# 检索与报告生成的边界

2026-11-04 已核对 DeepSeek 官方文档：

- Responses 的 max_tool_calls 被忽略，不能用它实现硬预算；previous_response_id 不受支持，服务端不保存响应历史。
- Search/Fetch 可用同一账户密钥，分别调用 /v1/tools/search 和 /v1/tools/fetch。
- 因此本项目改由 retrieval.py 固定最多4次搜索、4次读取，再以 tools=[]、tool_choice=none 和 JSON Schema 生成最终报告。模型没有追加搜索的入口。
- 真实来源ID、URL和取得状态由程序生成来源表。模型只能提出“适用事实”映射，该映射本身仍需核验。图表数字还要存在于本次实际取得的正文节选中。
- Fetch API 的404不是目标网站的404；按官方说明，站点策略、内容格式和无可提取正文等也可能造成这一响应，不据此宣称反爬或资源不存在。
- 失败时不自动重试。usage只表示接口返回的计数；错误若未返回usage，不能反推出消费为零。货币金额应以账单为准。

官方参考：

- https://api-docs.deepseek.com/guides/responses_api/
- https://api-docs.deepseek.com/api/create-response/
- https://api-docs.deepseek.com/api/search/
- https://api-docs.deepseek.com/api/fetch/
- https://api-docs.deepseek.com/guides/search/

此说明不是永久价格承诺；调用前按当时官方价格和账户权限为准。

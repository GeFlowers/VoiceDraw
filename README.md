# Voice Draw Studio

VoiceDraw 是一个语音驱动的 AI 矢量绘图工具。用户可以通过中文语音描述画面，后端会调用 OpenAI-compatible AI API，把语音识别文本转换为前端可执行的绘图计划，然后由浏览器 Canvas 渲染。

## 当前架构

- AI-first 规划：每条绘图命令都会优先进入 AI API，不再因为本地规则命中而跳过模型。
- 矢量路径协议：AI 可以返回 `draw_path`，使用 `M/L/Q/C/Z` 路径命令绘制复杂轮廓，不再只能依赖固定图形枚举。
- 本地兜底：AI 调用失败时才进入规则解析，并在返回值和日志里明确标记为兜底。
- 可观测日志：服务日志会输出 `ai_api_call_started` 和 `ai_api_call_completed`，同时前端展示来源、模型、延迟、操作数和置信度。
- 企业化工作台：前端改为深色工具台布局，包含快捷操作、画布状态、命令控制台、AI 调用面板和历史记录。

## 技术栈

- Python 3.11+
- Uvicorn ASGI
- 标准库 `urllib` 调用 OpenAI-compatible `/chat/completions`
- 浏览器 Web Speech API
- HTML Canvas

## 配置

复制并填写 `.env`：

```env
APP_ENV=development
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4o-mini
ENABLE_LLM=true
LLM_TIMEOUT_SECONDS=8
```

`LLM_BASE_URL` 可以是兼容 OpenAI 的 base URL，例如 `https://api.openai.com/v1`，也可以直接配置到 `/chat/completions`。

## 启动

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

建议使用最新版 Chrome 或 Edge。语音输入依赖浏览器麦克风授权。

## API

### 健康检查

```http
GET /api/health
```

返回示例：

```json
{
  "status": "ok",
  "env": "development",
  "llm_ready": true,
  "llm_model": "gpt-4o-mini",
  "planner_mode": "ai_first_vector_planner"
}
```

### 命令解析

```http
POST /api/commands/interpret
```

请求示例：

```json
{
  "transcript": "画一辆红色自行车，旁边写上 Demo",
  "locale": "zh-CN",
  "canvas_width": 1280,
  "canvas_height": 720,
  "selected_ids": [],
  "recent_object_ids": []
}
```

返回值是 `CommandPlan`。常见操作包括：

- `draw_path`：AI 生成的自由矢量路径。
- `draw_shape`：圆、矩形、线、箭头等明确几何体。
- `add_text`：添加文字。
- `move`、`resize`、`rotate`、`set_style`、`select`、`delete`：编辑已有对象。
- `clear`、`undo`、`redo`、`export`：画布操作。

## 日志

当 AI API 被调用时，uvicorn 日志中会出现：

```text
[voice-draw] ai_api_call_started model=gpt-4o-mini endpoint=https://.../v1/chat/completions
[voice-draw] ai_api_call_completed latency_ms=2140
```

如果 API 失败，返回计划会包含：

```json
{
  "source": "repaired",
  "metadata": {
    "llm_attempted": true,
    "planner": "rule_fallback_after_ai_error"
  }
}
```

如果未配置 AI API，后端会返回 `no_op`，不会静默使用规则解析伪装成正常绘图。

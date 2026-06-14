# VoiceDraw

## 1. 项目简介

VoiceDraw 是一个语音驱动的 AI 矢量绘图工具。用户通过中文语音描述想画什么或想怎样编辑画布，浏览器将语音识别结果提交给后端，后端调用 OpenAI-compatible AI API 生成结构化绘图计划，前端再根据计划在 HTML Canvas 上绘制。

## 2. 当前功能

### 2.1 语音输入

前端使用浏览器 Web Speech API 进行中文语音识别。

支持：

1. 麦克风语音输入。
2. 实时显示识别中的语音文本。
3. 识别完成后自动提交给后端 AI。

### 2.2 AI 绘图规划

后端会把用户语音识别文本发送给 AI，并要求 AI 从固定枚举中生成绘图计划。 支持的主要操作包括：

1. 绘制基础图形：`draw_shape`。
2. 绘制自由路径：`draw_path`。
3. 添加文字：`add_text`。
4. 修改样式：`set_style`。
5. 修改背景：`set_background`。
6. 修改画布尺寸：`set_canvas_size`。
7. 选择、删除、移动、缩放、旋转对象。
8. 清空、撤销、重做、导出画布。

### 2.3 Canvas 绘制

前端使用 HTML Canvas 渲染 AI 返回的操作。

支持的图形包括：

1. 线条、箭头、矩形、圆形、椭圆、三角形。
2. 菱形、五边形、六边形、星形、爱心。
3. 花朵、云朵、太阳、树、房子、山、笑脸、闪电。
4. 文字对象。
5. `M/L/Q/C/Z` 组成的自由矢量路径。

### 2.4 状态展示

前端会展示：

1. AI 连接状态。
2. 当前模型。
3. AI 调用延时。
4. 本次操作数。
5. AI 规划置信度。
6. 历史记录数。

## 3. 项目结构

```text
VoiceDraw/
  backend/
    config.py
    main.py
    models.py
    llm_parser.py
    validators.py
  fronted/
    index.html
    app.js
    styles.css
  .env.example
  .gitignore
  DESIGN.md
  README.md
  requirements.txt
```

## 4. 环境要求

1. Python 3.11 或更高版本。
2. 可用的 OpenAI-compatible `/chat/completions` API。
3. 支持 Web Speech API 的浏览器，建议使用最新版 Chrome 或 Edge。
4. 浏览器需要允许麦克风权限。

## 5. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

## 6. 配置环境变量

复制 `.env.example` 为 `.env`：

```powershell
Copy-Item .env.example .env
```

填写 AI API 配置：

```env
APP_ENV=development
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4o-mini
ENABLE_LLM=true
LLM_TIMEOUT_SECONDS=8
```

`LLM_BASE_URL` 可以填写兼容 OpenAI 的 base URL，例如：

```text
https://api.openai.com/v1
```

## 7. 启动项目

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 8. API

### 8.1 健康检查

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
  "planner_mode": "ai_enum_vector_planner"
}
```

### 8.2 语音命令解析

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

返回值是 `CommandPlan`，其中 `operations` 会由前端执行。

## 9. 日志

当 AI API 被调用时，uvicorn 日志会出现：

```text
[voice-draw] ai_api_call_started model=gpt-4o-mini endpoint=https://.../v1/chat/completions
[voice-draw] ai_api_call_completed latency_ms=2140
```

如果 AI 未配置或调用失败，后端会返回错误。

## 10. 当前限制

1. 必须配置可用的 AI API。
2. AI 输出质量会直接影响绘图质量。
3. 画布对象只保存在浏览器运行时内存中，刷新页面会丢失。
4. 综合考虑后，删除了本地规则兜底。

# Voice Draw

Voice Draw 是一款纯语音控制的 AI 绘图工具。用户打开页面后，通过中文语音完成绘图、选择、移动、缩放、旋转、撤销、清空和导出等操作。后端使用 LangChain 与 LangGraph 组织指令理解流程，前端使用浏览器 Web Speech API 和 Canvas 渲染画布。

## 核心能力

- 纯语音交互：前端自动启动语音识别，识别结果直接进入绘图指令解析流程。
- 低延迟规则解析：常见命令优先走本地规则解析，减少 LLM 调用等待。
- AI 兜底解析：当规则置信度不足且 `.env` 已配置模型地址与 API Key 时，使用 LangChain 调用 OpenAI 兼容接口。
- LangGraph 工作流：归一化、规则解析、LLM 兜底、计划校验与修复被拆成独立图节点。
- 复杂指令拆解：支持“画一个红色圆，然后在右边画蓝色矩形”这类多步骤语音命令。
- 工程化容错：统一 Pydantic 模型、指令校验、默认几何修复、错误反馈和前端执行队列。

## 技术栈

- Python 3.11+
- FastAPI
- Pydantic / Pydantic Settings
- LangChain
- LangGraph
- LangChain OpenAI
- 浏览器 Web Speech API
- HTML Canvas

## 项目结构

```text
.
├── backend/
│   └── app/
│       ├── config.py
│       ├── main.py
│       ├── domain/
│       │   └── models.py
│       ├── services/
│       │   ├── colors.py
│       │   ├── interpreter_graph.py
│       │   ├── llm_parser.py
│       │   ├── rule_parser.py
│       │   ├── text_normalizer.py
│       │   └── validators.py
│       └── static/
│           ├── index.html
│           ├── styles.css
│           └── app.js
├── docs/
│   └── design.md
├── .env
├── .env.example
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

### 2. 配置 `.env`

项目已提供 `.env` 文件，请填写你的模型服务地址和 API Key：

```env
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini
ENABLE_LLM=true
RULE_CONFIDENCE_THRESHOLD=0.72
LLM_TIMEOUT_SECONDS=8
```

`LLM_BASE_URL` 需要是 OpenAI 兼容接口地址。若不填写 `LLM_BASE_URL` 或 `LLM_API_KEY`，常见命令仍会使用本地规则解析执行，但低置信度复杂指令不会进入 LLM 兜底。

### 3. 启动服务

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

建议使用最新版 Chrome 或 Edge。浏览器首次使用麦克风时会弹出权限确认，这是浏览器安全限制，应用代码无法绕过。

## 支持的语音示例

### 绘制图形

- `画一个红色圆`
- `在右边画蓝色矩形`
- `画一条从左上角到右下角的粗线`
- `画一个黄色实心三角形`
- `画一个虚线箭头`

### 场景预设

- `画太阳`
- `画一座房子`
- `画一棵树`
- `画云朵和山`
- `画太阳和一棵树`

### 文字

- `在顶部写上标题 Voice Draw`
- `在中间添加文字 你好`

### 对象操作

- `选择最后一个`
- `全部选中`
- `向右移动一点`
- `向下移动 40`
- `放大`
- `缩小百分之二十`
- `顺时针旋转 30 度`
- `删除选中对象`

### 画布操作

- `撤销`
- `重做`
- `清空画布`
- `背景改成白色`
- `背景透明`
- `导出图片`

### 复合指令

- `画一个红色圆，然后在右边画蓝色矩形，再在顶部写上标题 Voice Draw`

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
  "llm_ready": false
}
```

### 指令解析

```http
POST /api/commands/interpret
```

请求示例：

```json
{
  "transcript": "画一个红色圆，然后在右边画蓝色矩形",
  "locale": "zh-CN",
  "canvas_width": 1280,
  "canvas_height": 720,
  "selected_ids": [],
  "recent_object_ids": []
}
```

返回值是 `CommandPlan`，其中 `operations` 为前端可执行的绘图动作列表。

## 工程化设计

- 领域模型集中在 `backend/domain/models.py`，避免前后端协议散落。
- 规则解析位于 `backend/services/rule_parser.py`，LLM 解析位于 `backend/services/llm_parser.py`。
- LangGraph 工作流位于 `backend/services/interpreter_graph.py`。
- 校验和修复逻辑位于 `backend/services/validators.py`。
- 前端维护操作队列，避免连续语音输入造成并发覆盖。
- 每次复合语音指令作为一个历史快照，撤销行为符合用户预期。

## 已知限制

- 浏览器首次麦克风授权无法做到完全无鼠标/键盘，这是浏览器安全策略限制。
- 当前绘图输出为 Canvas 矢量/几何绘制，不包含扩散模型生成位图。
- 对象选择支持 `selected`、`last`、`all`，暂未实现“选择左边那个红色圆”这类视觉检索。
- 语音识别质量取决于浏览器 Web Speech API 和系统麦克风环境。

更多设计细节见 [docs/design.md](docs/design.md)。

# VoiceDraw 设计文档

## 1. 项目定位

VoiceDraw 是一个中文语音驱动的 AI 矢量绘图原型。项目目标是让用户通过自然语言描述绘图意图，由后端 AI 生成结构化绘图计划，再由前端 Canvas 执行这些计划。

## 2. 设计目标

1. 使用语音作为主要输入方式。
2. 使用 AI 理解自然语言，而不是本地关键词规则。
3. 使用固定枚举约束 AI 输出，降低前端无法执行的风险。
4. 使用 Canvas 渲染基础图形和矢量路径。
5. 保持后端结构简单，便于阅读和继续扩展。

## 3. 非目标

1. 不实现本地规则兜底。
2. 不实现账号系统。
3. 不实现云端存储。
4. 不实现完整专业矢量编辑器能力。
5. 不实现文字输入测试入口。
6. 不实现语音朗读反馈。

## 4. 当前目录结构

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

## 5. 后端设计

### 5.1 `config.py`

职责：

1. 读取 `.env` 文件。
2. 读取系统环境变量。
3. 构造 `Settings` 配置对象。
4. 判断 AI API 是否已配置完成。

### 5.2 `models.py`

职责：

1. 定义前后端通信协议。
2. 定义 AI 可用的操作枚举。
3. 定义 AI 可用的图形枚举。
4. 使用 Pydantic 校验请求和返回数据。

### 5.3 `main.py`

职责：

1. 作为 ASGI 应用入口。
2. 提供 `/api/health`。
3. 提供 `/api/commands/interpret`。
4. 托管前端静态页面。
5. 编排 AI 规划和计划校验流程。

### 5.4 `llm_parser.py`

职责：

1. 定义 AI prompt。
2. 向 AI 展示可用枚举。
3. 调用 OpenAI-compatible `/chat/completions`。
4. 提取 AI 返回的 JSON。
5. 兼容少量常见字段变体。
6. 构造 `CommandPlan`。

AI 必须从以下枚举中生成计划：

1. `OperationType`
2. `ShapeType`
3. `TargetSelector`
4. `PathCommand`

### 5.5 `validators.py`

职责：

1. 检查 AI 返回的操作是否完整。
2. 过滤前端无法执行的操作。
3. 给变换类操作补默认目标。
4. 保证返回计划中至少有一个操作。

## 6. 前端设计

### 6.1 页面结构

前端由三份静态文件组成：

1. `fronted/index.html`
2. `fronted/app.js`
3. `fronted/styles.css`

页面主要区域：

1. 顶部状态栏。
2. Canvas 画布区。
3. 右侧活动面板。
4. AI 调用信息面板。
5. 历史记录面板。

### 6.2 语音输入

前端使用浏览器 Web Speech API。

支持：

1. 中文语音识别。
2. 临时识别文本展示。
3. 最终识别文本自动提交。

### 6.3 Canvas 执行

前端根据 `operations` 执行绘图。

支持：

1. 基础形状绘制。
2. 自由路径绘制。
3. 文字绘制。
4. 背景色修改。
5. 画布尺寸修改。
6. 对象选择、删除、移动、缩放、旋转。
7. 撤销、重做、导出。

## 7. 支持的功能

### 7.1 操作类型

当前支持：

1. `draw_shape`
2. `draw_path`
3. `add_text`
4. `set_style`
5. `set_background`
6. `set_canvas_size`
7. `select`
8. `delete`
9. `move`
10. `resize`
11. `rotate`
12. `clear`
13. `undo`
14. `redo`
15. `export`
16. `announce`
17. `no_op`

### 7.2 图形类型

当前支持：

1. `path`
2. `line`
3. `arrow`
4. `rectangle`
5. `circle`
6. `ellipse`
7. `triangle`
8. `diamond`
9. `pentagon`
10. `hexagon`
11. `star`
12. `heart`
13. `flower`
14. `cloud`
15. `sun`
16. `tree`
17. `house`
18. `mountain`
19. `smile`
20. `lightning`
21. `text`

### 7.3 路径命令

当前支持：

1. `M`：移动到某点。
2. `L`：画直线到某点。
3. `Q`：二次贝塞尔曲线。
4. `C`：三次贝塞尔曲线。
5. `Z`：闭合路径。

## 8. 执行流程

### 8.1 页面访问流程

```text
浏览器访问 /
  -> backend/main.py
  -> 查找前端目录
  -> 返回 index.html
```

### 8.2 语音命令流程

```text
用户语音输入
  -> 浏览器 Web Speech API
  -> fronted/app.js
  -> POST /api/commands/interpret
  -> backend/main.py
  -> CommandRequest
  -> LLMCommandParser
  -> AI API
  -> CommandPlan
  -> PlanValidator
  -> JSON 返回前端
  -> Canvas 执行 operations
```

## 9. 想实现但当前未实现的功能

### 9.1 对象持久化保存

未实现内容：

1. 保存画布项目文件。
2. 重新打开历史项目。
3. 持久化对象列表和编辑历史。

未实现原因：

当前项目没有数据库、文件存储或用户系统。前端对象状态只保存在浏览器运行时内存中，刷新页面后会丢失。

### 9.2 多用户和账号系统

未实现内容：

1. 用户登录。
2. 用户项目隔离。
3. 云端同步。
4. 权限管理。

未实现原因：

当前项目定位是本地单用户演示工具，后端没有认证、会话、数据库和用户模型。

### 9.3 更完整的样式编辑

未实现内容：

1. 渐变填充。
2. 阴影。
3. 端点样式。
4. 线帽样式。
5. 字体选择。
6. 字号独立控制。

未实现原因：

当前样式协议只包含 `stroke`、`fill`、`line_width`、`opacity`、`dashed`。复杂样式需要扩展后端模型、AI 输出协议和 Canvas 渲染逻辑。

### 9.4 AI 结果可视化确认

未实现内容：

1. AI 先预览计划。
2. 用户确认后再绘制。
3. 展示 AI 拆解出的每个操作。
4. 用户手动删除某个操作。

未实现原因：

当前交互路径是 AI 返回后立即执行，没有中间确认态。实现该功能需要前端增加计划预览 UI 和操作队列管理。

### 9.5 AI 失败重试和模型降级

未实现内容：

1. 自动重试。
2. 多模型 fallback。
3. 超时后切换备用模型。
4. 更细粒度错误提示。

未实现原因：

当前后端只配置一个 OpenAI-compatible endpoint 和一个模型。系统已经移除本地规则兜底，因此 AI 不可用时直接报错。
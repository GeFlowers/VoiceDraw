const canvas = document.querySelector("#drawingCanvas");
const ctx = canvas.getContext("2d");
const statusText = document.querySelector("#statusText");
const signalText = document.querySelector("#signalText");
const listenDot = document.querySelector("#listenDot");
const transcriptText = document.querySelector("#transcriptText");
const activityLog = document.querySelector("#activityLog");
const objectCount = document.querySelector("#objectCount");
const selectionCount = document.querySelector("#selectionCount");

const state = {
  objects: [],
  selectedIds: [],
  undoStack: [],
  redoStack: [],
  background: "#fffefa",
  viewport: { width: 1, height: 1 },
  processing: false,
  queue: [],
};

const mutatingTypes = new Set([
  "draw_shape",
  "add_text",
  "set_style",
  "set_background",
  "delete",
  "move",
  "resize",
  "rotate",
  "clear",
]);

let recognition = null;
let recognitionActive = false;
let restartTimer = null;
let voiceBlocked = false;

function setStatus(kind, message) {
  listenDot.classList.remove("listening", "processing", "error");
  if (kind) listenDot.classList.add(kind);
  signalText.textContent = message;
  statusText.textContent = message;
}

function speak(message) {
  if (!message || !("speechSynthesis" in window)) return;
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = "zh-CN";
  utterance.rate = 1.05;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  state.viewport = {
    width: Math.max(1, Math.floor(rect.width)),
    height: Math.max(1, Math.floor(rect.height)),
  };
  canvas.width = Math.floor(state.viewport.width * dpr);
  canvas.height = Math.floor(state.viewport.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  render();
}

function snapshot() {
  return JSON.stringify({
    objects: state.objects,
    selectedIds: state.selectedIds,
    background: state.background,
  });
}

function restore(serialized) {
  const parsed = JSON.parse(serialized);
  state.objects = parsed.objects || [];
  state.selectedIds = parsed.selectedIds || [];
  state.background = parsed.background || "#fffefa";
}

function pushHistory() {
  state.undoStack.push(snapshot());
  if (state.undoStack.length > 80) state.undoStack.shift();
  state.redoStack = [];
}

function applyPlan(plan, transcript) {
  const operations = Array.isArray(plan.operations) ? plan.operations : [];
  const shouldSnapshot = operations.some((operation) => mutatingTypes.has(operation.type));
  if (shouldSnapshot) pushHistory();

  for (const operation of operations) {
    applyOperation(operation);
  }
  render();
  updateMetrics();
  addLog(transcript, plan.spoken_feedback || "指令已处理");
  speak(plan.spoken_feedback || "指令已处理");
}

function applyOperation(operation) {
  switch (operation.type) {
    case "draw_shape":
    case "add_text":
      addObject(operation);
      break;
    case "set_style":
      updateStyle(operation);
      break;
    case "set_background":
      state.background = operation.value || "#fffefa";
      break;
    case "select":
      selectTarget(operation.target);
      break;
    case "delete":
      deleteTarget(operation.target);
      break;
    case "move":
      moveTarget(operation.target, operation.delta || { dx: 0, dy: 0 });
      break;
    case "resize":
      resizeTarget(operation.target, operation.amount || 1);
      break;
    case "rotate":
      rotateTarget(operation.target, operation.amount || 0);
      break;
    case "clear":
      state.objects = [];
      state.selectedIds = [];
      break;
    case "undo":
      undo();
      break;
    case "redo":
      redo();
      break;
    case "export":
      exportCanvas();
      break;
    case "announce":
    case "no_op":
    default:
      break;
  }
}

function addObject(operation) {
  const id = `obj_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const object = {
    id,
    type: operation.type === "add_text" ? "text" : operation.shape,
    text: operation.text || "",
    geometry: { ...(operation.geometry || {}) },
    style: normalizeStyle(operation.style || {}),
    rotation: 0,
  };
  state.objects.push(object);
  state.selectedIds = [id];
}

function normalizeStyle(style) {
  return {
    stroke: style.stroke || "#1f2937",
    fill: style.fill || null,
    lineWidth: style.line_width || style.lineWidth || 4,
    opacity: style.opacity ?? 1,
    dashed: Boolean(style.dashed),
  };
}

function selectTarget(target = "selected") {
  if (target === "all") {
    state.selectedIds = state.objects.map((object) => object.id);
  } else if (target === "last") {
    const last = state.objects[state.objects.length - 1];
    state.selectedIds = last ? [last.id] : [];
  } else if (target === "none") {
    state.selectedIds = [];
  }
}

function getTargets(target = "selected") {
  if (target === "all") return state.objects;
  if (target === "last") return state.objects.length ? [state.objects[state.objects.length - 1]] : [];
  if (!state.selectedIds.length && state.objects.length) return [state.objects[state.objects.length - 1]];
  return state.objects.filter((object) => state.selectedIds.includes(object.id));
}

function deleteTarget(target = "selected") {
  const ids = new Set(getTargets(target).map((object) => object.id));
  state.objects = state.objects.filter((object) => !ids.has(object.id));
  state.selectedIds = state.selectedIds.filter((id) => !ids.has(id));
}

function updateStyle(operation) {
  const style = normalizeStyle(operation.style || {});
  for (const object of getTargets(operation.target)) {
    object.style = { ...object.style, ...style };
  }
}

function moveTarget(target, delta) {
  for (const object of getTargets(target)) {
    translateGeometry(object.geometry, delta.dx || 0, delta.dy || 0);
  }
}

function resizeTarget(target, amount) {
  for (const object of getTargets(target)) {
    scaleGeometry(object.geometry, amount);
  }
}

function rotateTarget(target, amount) {
  for (const object of getTargets(target)) {
    object.rotation = (object.rotation || 0) + amount;
  }
}

function undo() {
  if (!state.undoStack.length) return;
  state.redoStack.push(snapshot());
  restore(state.undoStack.pop());
}

function redo() {
  if (!state.redoStack.length) return;
  state.undoStack.push(snapshot());
  restore(state.redoStack.pop());
}

function exportCanvas() {
  const link = document.createElement("a");
  link.download = `voice-draw-${new Date().toISOString().replace(/[:.]/g, "-")}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

function translateGeometry(geometry, dx, dy) {
  for (const key of ["x", "x2"]) {
    if (typeof geometry[key] === "number") geometry[key] = clamp(geometry[key] + dx);
  }
  for (const key of ["y", "y2"]) {
    if (typeof geometry[key] === "number") geometry[key] = clamp(geometry[key] + dy);
  }
}

function scaleGeometry(geometry, amount) {
  for (const key of ["width", "height", "radius"]) {
    if (typeof geometry[key] === "number") geometry[key] = clamp(geometry[key] * amount, 0.01, 1);
  }
  if (typeof geometry.x === "number" && typeof geometry.x2 === "number") {
    const cx = (geometry.x + geometry.x2) / 2;
    geometry.x = clamp(cx + (geometry.x - cx) * amount);
    geometry.x2 = clamp(cx + (geometry.x2 - cx) * amount);
  }
  if (typeof geometry.y === "number" && typeof geometry.y2 === "number") {
    const cy = (geometry.y + geometry.y2) / 2;
    geometry.y = clamp(cy + (geometry.y - cy) * amount);
    geometry.y2 = clamp(cy + (geometry.y2 - cy) * amount);
  }
}

function render() {
  ctx.clearRect(0, 0, state.viewport.width, state.viewport.height);
  if (state.background !== "transparent") {
    ctx.fillStyle = state.background;
    ctx.fillRect(0, 0, state.viewport.width, state.viewport.height);
  }

  for (const object of state.objects) {
    drawObject(object);
  }
  for (const object of getTargets("selected")) {
    drawSelection(object);
  }
}

function drawObject(object) {
  const style = object.style || normalizeStyle({});
  ctx.save();
  ctx.globalAlpha = style.opacity;
  ctx.lineWidth = style.lineWidth;
  ctx.strokeStyle = style.stroke;
  ctx.fillStyle = style.fill || "transparent";
  ctx.setLineDash(style.dashed ? [10, 7] : []);
  applyRotation(object, () => {
    switch (object.type) {
      case "line":
        drawLine(object.geometry, false);
        break;
      case "arrow":
        drawLine(object.geometry, true);
        break;
      case "rectangle":
        drawRectangle(object.geometry);
        break;
      case "circle":
        drawCircle(object.geometry);
        break;
      case "ellipse":
        drawEllipse(object.geometry);
        break;
      case "triangle":
        drawTriangle(object.geometry);
        break;
      case "text":
        drawText(object);
        break;
      default:
        break;
    }
  });
  ctx.restore();
}

function applyRotation(object, drawFn) {
  const bounds = getBounds(object);
  const cx = bounds.x + bounds.width / 2;
  const cy = bounds.y + bounds.height / 2;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(((object.rotation || 0) * Math.PI) / 180);
  ctx.translate(-cx, -cy);
  drawFn();
  ctx.restore();
}

function drawLine(geometry, withArrow) {
  const x1 = px(geometry.x ?? 0.2);
  const y1 = py(geometry.y ?? 0.5);
  const x2 = px(geometry.x2 ?? 0.8);
  const y2 = py(geometry.y2 ?? 0.5);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  if (withArrow) drawArrowHead(x1, y1, x2, y2);
}

function drawArrowHead(x1, y1, x2, y2) {
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const size = 16;
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - size * Math.cos(angle - Math.PI / 6), y2 - size * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(x2 - size * Math.cos(angle + Math.PI / 6), y2 - size * Math.sin(angle + Math.PI / 6));
  ctx.closePath();
  ctx.fillStyle = ctx.strokeStyle;
  ctx.fill();
}

function drawRectangle(geometry) {
  const width = pw(geometry.width ?? 0.25);
  const height = ph(geometry.height ?? 0.18);
  const x = px(geometry.x ?? 0.5) - width / 2;
  const y = py(geometry.y ?? 0.5) - height / 2;
  if (geometry.fill !== null) ctx.fillRect(x, y, width, height);
  if (ctx.strokeStyle) ctx.strokeRect(x, y, width, height);
}

function drawCircle(geometry) {
  const radius = Math.min(pw(geometry.radius ?? 0.1), ph(geometry.radius ?? 0.1));
  ctx.beginPath();
  ctx.arc(px(geometry.x ?? 0.5), py(geometry.y ?? 0.5), radius, 0, Math.PI * 2);
  fillAndStroke();
}

function drawEllipse(geometry) {
  const width = pw(geometry.width ?? 0.24);
  const height = ph(geometry.height ?? 0.14);
  ctx.beginPath();
  ctx.ellipse(px(geometry.x ?? 0.5), py(geometry.y ?? 0.5), width / 2, height / 2, 0, 0, Math.PI * 2);
  fillAndStroke();
}

function drawTriangle(geometry) {
  const width = pw(geometry.width ?? 0.24);
  const height = ph(geometry.height ?? 0.22);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  ctx.beginPath();
  ctx.moveTo(x, y - height / 2);
  ctx.lineTo(x + width / 2, y + height / 2);
  ctx.lineTo(x - width / 2, y + height / 2);
  ctx.closePath();
  fillAndStroke();
}

function drawText(object) {
  const geometry = object.geometry || {};
  const fontSize = Math.max(14, ph(geometry.height ?? 0.08));
  ctx.font = `700 ${fontSize}px Inter, Microsoft YaHei, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = object.style.fill || object.style.stroke || "#111827";
  ctx.fillText(object.text, px(geometry.x ?? 0.5), py(geometry.y ?? 0.5));
}

function fillAndStroke() {
  if (ctx.fillStyle !== "transparent") ctx.fill();
  ctx.stroke();
}

function drawSelection(object) {
  const bounds = getBounds(object);
  ctx.save();
  ctx.strokeStyle = "#2f6fed";
  ctx.lineWidth = 2;
  ctx.setLineDash([7, 5]);
  ctx.strokeRect(bounds.x - 6, bounds.y - 6, bounds.width + 12, bounds.height + 12);
  ctx.restore();
}

function getBounds(object) {
  const geometry = object.geometry || {};
  if (object.type === "line" || object.type === "arrow") {
    const x1 = px(geometry.x ?? 0.2);
    const y1 = py(geometry.y ?? 0.5);
    const x2 = px(geometry.x2 ?? 0.8);
    const y2 = py(geometry.y2 ?? 0.5);
    return {
      x: Math.min(x1, x2),
      y: Math.min(y1, y2),
      width: Math.max(1, Math.abs(x2 - x1)),
      height: Math.max(1, Math.abs(y2 - y1)),
    };
  }
  const width = object.type === "circle" ? pw((geometry.radius ?? 0.1) * 2) : pw(geometry.width ?? 0.25);
  const height = object.type === "circle" ? ph((geometry.radius ?? 0.1) * 2) : ph(geometry.height ?? 0.18);
  return {
    x: px(geometry.x ?? 0.5) - width / 2,
    y: py(geometry.y ?? 0.5) - height / 2,
    width,
    height,
  };
}

function px(value) {
  return value * state.viewport.width;
}

function py(value) {
  return value * state.viewport.height;
}

function pw(value) {
  return value * state.viewport.width;
}

function ph(value) {
  return value * state.viewport.height;
}

function clamp(value, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}

function updateMetrics() {
  objectCount.textContent = String(state.objects.length);
  selectionCount.textContent = String(state.selectedIds.length);
}

function addLog(transcript, feedback) {
  const item = document.createElement("li");
  const title = document.createElement("strong");
  title.textContent = transcript;
  const body = document.createElement("span");
  body.textContent = feedback;
  item.append(title, body);
  activityLog.prepend(item);
  while (activityLog.children.length > 20) {
    activityLog.removeChild(activityLog.lastChild);
  }
}

async function enqueueTranscript(transcript) {
  const normalized = transcript.trim();
  if (!normalized) return;
  state.queue.push(normalized);
  transcriptText.textContent = normalized;
  await processQueue();
}

async function processQueue() {
  if (state.processing) return;
  state.processing = true;
  while (state.queue.length) {
    const transcript = state.queue.shift();
    setStatus("processing", "解析指令");
    try {
      const response = await fetch("/api/commands/interpret", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript,
          locale: navigator.language || "zh-CN",
          canvas_width: state.viewport.width,
          canvas_height: state.viewport.height,
          selected_ids: state.selectedIds,
          recent_object_ids: state.objects.slice(-10).map((object) => object.id),
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const plan = await response.json();
      applyPlan(plan, transcript);
    } catch (error) {
      const message = `指令处理失败: ${error.message}`;
      addLog(transcript, message);
      speak(message);
      setStatus("error", "处理失败");
    }
  }
  state.processing = false;
  if (recognitionActive) setStatus("listening", "正在聆听");
}

function initVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setStatus("error", "当前浏览器不支持语音识别");
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "zh-CN";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    recognitionActive = true;
    setStatus("listening", "正在聆听");
  };

  recognition.onerror = (event) => {
    if (event.error === "not-allowed" || event.error === "service-not-allowed") {
      voiceBlocked = true;
    }
    setStatus("error", event.error === "not-allowed" ? "麦克风未授权" : "语音识别异常");
  };

  recognition.onend = () => {
    recognitionActive = false;
    clearTimeout(restartTimer);
    if (!voiceBlocked) {
      restartTimer = setTimeout(() => startListening(), 600);
    }
  };

  recognition.onresult = (event) => {
    let finalTranscript = "";
    let interimTranscript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (result.isFinal) {
        finalTranscript += result[0].transcript;
      } else {
        interimTranscript += result[0].transcript;
      }
    }
    if (interimTranscript) transcriptText.textContent = interimTranscript;
    if (finalTranscript) enqueueTranscript(finalTranscript);
  };

  startListening();
}

function startListening() {
  if (!recognition || recognitionActive || voiceBlocked) return;
  try {
    recognition.start();
  } catch {
    clearTimeout(restartTimer);
    restartTimer = setTimeout(() => startListening(), 1000);
  }
}

window.addEventListener("resize", resizeCanvas);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") startListening();
});

resizeCanvas();
updateMetrics();
initVoice();

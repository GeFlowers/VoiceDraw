const canvas = document.querySelector("#drawingCanvas");
const ctx = canvas.getContext("2d");
const signalText = document.querySelector("#signalText");
const listenDot = document.querySelector("#listenDot");
const transcriptText = document.querySelector("#transcriptText");
const activityLog = document.querySelector("#activityLog");
const objectCount = document.querySelector("#objectCount");
const selectionCount = document.querySelector("#selectionCount");
const testCommandForm = document.querySelector("#testCommandForm");
const testCommandInput = document.querySelector("#testCommandInput");
const aiStatusText = document.querySelector("#aiStatusText");
const sourceText = document.querySelector("#sourceText");
const confidenceText = document.querySelector("#confidenceText");
const latencyText = document.querySelector("#latencyText");
const modelText = document.querySelector("#modelText");
const operationCountText = document.querySelector("#operationCountText");
const historyCountText = document.querySelector("#historyCountText");
const canvasSizeText = document.querySelector("#canvasSizeText");

const DEFAULT_CANVAS_SIZE = { width: 1280, height: 720 };
const MIN_CANVAS_SIZE = 240;
const MAX_CANVAS_SIZE = 4096;

const state = {
  objects: [],
  selectedIds: [],
  undoStack: [],
  redoStack: [],
  background: "#fffefa",
  canvasSize: { ...DEFAULT_CANVAS_SIZE },
  viewport: { ...DEFAULT_CANVAS_SIZE },
  processing: false,
  queue: [],
};

const mutatingTypes = new Set([
  "draw_shape",
  "draw_path",
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
let SpeechRecognitionCtor = null;
let recognitionActive = false;
let restartTimer = null;
let voiceBlocked = false;
let voiceRestarting = false;

function setStatus(kind, message) {
  listenDot.classList.remove("listening", "processing", "error");
  if (kind) listenDot.classList.add(kind);
  document.body.dataset.state = kind || "idle";
  signalText.textContent = message;
}

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  state.viewport = { ...state.canvasSize };
  canvas.style.setProperty("--canvas-width", String(state.canvasSize.width));
  canvas.style.setProperty("--canvas-height", String(state.canvasSize.height));
  canvas.width = Math.floor(state.viewport.width * dpr);
  canvas.height = Math.floor(state.viewport.height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (canvasSizeText) canvasSizeText.textContent = `${state.viewport.width} x ${state.viewport.height}`;
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

  const drawOperations = operations.filter((operation) =>
    ["draw_shape", "draw_path", "add_text"].includes(operation.type),
  );
  const planGroupId = drawOperations.length ? `group_${Date.now()}_${Math.random().toString(16).slice(2)}` : null;
  for (const operation of operations) {
    applyOperation(operation, planGroupId);
  }
  render();
  updateMetrics();
  updatePlanTelemetry(plan);
  addLog(transcript, plan.spoken_feedback || "指令已处理", plan);
}

function applyOperation(operation, planGroupId = null) {
  switch (operation.type) {
    case "draw_shape":
    case "draw_path":
    case "add_text":
      addObject(operation, operation.group_id || planGroupId);
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

function addObject(operation, groupId = null) {
  const id = `obj_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const object = {
    id,
    groupId: groupId || id,
    type: operation.type === "add_text" ? "text" : operation.type === "draw_path" ? "path" : operation.shape,
    text: operation.text || "",
    geometry: { ...(operation.geometry || {}) },
    path: normalizePath(operation.path || []),
    style: normalizeStyle(operation.style || {}),
    rotation: 0,
  };
  state.objects.push(object);
  state.selectedIds = getGroupObjects(object.groupId).map((item) => item.id);
}

function normalizePath(path) {
  if (!Array.isArray(path)) return [];
  const commands = [];
  for (const item of path) {
    if (!item || typeof item !== "object") continue;
    const command = String(item.command || "").toUpperCase();
    if (!["M", "L", "Q", "C", "Z"].includes(command)) continue;
    const normalized = { command };
    for (const key of ["x", "y", "x1", "y1", "x2", "y2"]) {
      if (typeof item[key] === "number") normalized[key] = clamp(item[key]);
    }
    commands.push(normalized);
  }
  return commands;
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
    state.selectedIds = last ? getGroupObjects(last.groupId).map((object) => object.id) : [];
  } else if (target === "none") {
    state.selectedIds = [];
  }
}

function getTargets(target = "selected") {
  if (target === "all") return state.objects;
  if (target === "last") {
    const last = state.objects[state.objects.length - 1];
    return last ? getGroupObjects(last.groupId) : [];
  }
  if (!state.selectedIds.length && state.objects.length) {
    const last = state.objects[state.objects.length - 1];
    return getGroupObjects(last.groupId);
  }
  const selectedGroupIds = new Set(
    state.objects
      .filter((object) => state.selectedIds.includes(object.id))
      .map((object) => object.groupId || object.id),
  );
  return state.objects.filter((object) => selectedGroupIds.has(object.groupId || object.id));
}

function getGroupObjects(groupId) {
  return state.objects.filter((object) => (object.groupId || object.id) === groupId);
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
    translateObject(object, delta.dx || 0, delta.dy || 0);
  }
}

function resizeTarget(target, amount) {
  for (const object of getTargets(target)) {
    scaleObject(object, amount);
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

function translateObject(object, dx, dy) {
  translateGeometry(object.geometry || {}, dx, dy);
  if (object.type === "path") {
    translatePath(object.path || [], dx, dy);
  }
}

function translatePath(path, dx, dy) {
  for (const command of path) {
    for (const key of ["x", "x1", "x2"]) {
      if (typeof command[key] === "number") command[key] = clamp(command[key] + dx);
    }
    for (const key of ["y", "y1", "y2"]) {
      if (typeof command[key] === "number") command[key] = clamp(command[key] + dy);
    }
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

function scaleObject(object, amount) {
  scaleGeometry(object.geometry || {}, amount);
  if (object.type !== "path") return;

  const bounds = getPathBoundsNormalized(object.path || []);
  const cx = bounds.x + bounds.width / 2;
  const cy = bounds.y + bounds.height / 2;
  for (const command of object.path || []) {
    for (const key of ["x", "x1", "x2"]) {
      if (typeof command[key] === "number") command[key] = clamp(cx + (command[key] - cx) * amount);
    }
    for (const key of ["y", "y1", "y2"]) {
      if (typeof command[key] === "number") command[key] = clamp(cy + (command[key] - cy) * amount);
    }
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
  for (const group of getSelectedGroups()) {
    drawSelection(group);
  }
}

function getSelectedGroups() {
  const selectedObjects = getTargets("selected");
  const groups = new Map();
  for (const object of selectedObjects) {
    const groupId = object.groupId || object.id;
    if (!groups.has(groupId)) groups.set(groupId, []);
    groups.get(groupId).push(object);
  }
  return [...groups.values()];
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
      case "path":
        drawPath(object.path || []);
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
      case "diamond":
        drawDiamond(object.geometry);
        break;
      case "pentagon":
        drawRegularPolygon(object.geometry, 5, -Math.PI / 2);
        break;
      case "hexagon":
        drawRegularPolygon(object.geometry, 6, Math.PI / 6);
        break;
      case "star":
        drawStar(object.geometry);
        break;
      case "heart":
        drawHeart(object.geometry);
        break;
      case "flower":
        drawFlower(object.geometry);
        break;
      case "cloud":
        drawCloud(object.geometry);
        break;
      case "sun":
        drawSun(object.geometry);
        break;
      case "tree":
        drawTree(object.geometry);
        break;
      case "house":
        drawHouse(object.geometry);
        break;
      case "mountain":
        drawMountain(object.geometry);
        break;
      case "smile":
        drawSmile(object.geometry);
        break;
      case "lightning":
        drawLightning(object.geometry);
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

function drawPath(path) {
  if (!Array.isArray(path) || !path.length) return;
  ctx.beginPath();
  for (const command of path) {
    switch (command.command) {
      case "M":
        ctx.moveTo(px(command.x ?? 0.5), py(command.y ?? 0.5));
        break;
      case "L":
        ctx.lineTo(px(command.x ?? 0.5), py(command.y ?? 0.5));
        break;
      case "Q":
        ctx.quadraticCurveTo(
          px(command.x1 ?? command.x ?? 0.5),
          py(command.y1 ?? command.y ?? 0.5),
          px(command.x ?? 0.5),
          py(command.y ?? 0.5),
        );
        break;
      case "C":
        ctx.bezierCurveTo(
          px(command.x1 ?? command.x ?? 0.5),
          py(command.y1 ?? command.y ?? 0.5),
          px(command.x2 ?? command.x ?? 0.5),
          py(command.y2 ?? command.y ?? 0.5),
          px(command.x ?? 0.5),
          py(command.y ?? 0.5),
        );
        break;
      case "Z":
        ctx.closePath();
        break;
      default:
        break;
    }
  }
  fillAndStroke();
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

function drawDiamond(geometry) {
  const width = pw(geometry.width ?? 0.24);
  const height = ph(geometry.height ?? 0.24);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  ctx.beginPath();
  ctx.moveTo(x, y - height / 2);
  ctx.lineTo(x + width / 2, y);
  ctx.lineTo(x, y + height / 2);
  ctx.lineTo(x - width / 2, y);
  ctx.closePath();
  fillAndStroke();
}

function drawRegularPolygon(geometry, sides, startAngle = 0) {
  const width = pw(geometry.width ?? 0.24);
  const height = ph(geometry.height ?? 0.24);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  const radius = Math.min(width, height) / 2;
  ctx.beginPath();
  for (let index = 0; index < sides; index += 1) {
    const angle = startAngle + (index / sides) * Math.PI * 2;
    const pxValue = x + Math.cos(angle) * radius;
    const pyValue = y + Math.sin(angle) * radius;
    if (index === 0) ctx.moveTo(pxValue, pyValue);
    else ctx.lineTo(pxValue, pyValue);
  }
  ctx.closePath();
  fillAndStroke();
}

function drawStar(geometry) {
  const width = pw(geometry.width ?? 0.26);
  const height = ph(geometry.height ?? 0.26);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  const outer = Math.min(width, height) / 2;
  const inner = outer * 0.42;
  ctx.beginPath();
  for (let index = 0; index < 10; index += 1) {
    const radius = index % 2 === 0 ? outer : inner;
    const angle = -Math.PI / 2 + (index / 10) * Math.PI * 2;
    const pxValue = x + Math.cos(angle) * radius;
    const pyValue = y + Math.sin(angle) * radius;
    if (index === 0) ctx.moveTo(pxValue, pyValue);
    else ctx.lineTo(pxValue, pyValue);
  }
  ctx.closePath();
  fillAndStroke();
}

function drawHeart(geometry) {
  const width = pw(geometry.width ?? 0.26);
  const height = ph(geometry.height ?? 0.24);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  ctx.beginPath();
  ctx.moveTo(x, y + height * 0.35);
  ctx.bezierCurveTo(x - width * 0.55, y, x - width * 0.38, y - height * 0.45, x, y - height * 0.18);
  ctx.bezierCurveTo(x + width * 0.38, y - height * 0.45, x + width * 0.55, y, x, y + height * 0.35);
  ctx.closePath();
  fillAndStroke();
}

function drawFlower(geometry) {
  const width = pw(geometry.width ?? 0.28);
  const height = ph(geometry.height ?? 0.26);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  const petalRadiusX = width * 0.16;
  const petalRadiusY = height * 0.28;
  const oldFill = ctx.fillStyle;
  for (let index = 0; index < 6; index += 1) {
    const angle = (index / 6) * Math.PI * 2;
    ctx.save();
    ctx.translate(x + Math.cos(angle) * width * 0.18, y + Math.sin(angle) * height * 0.18);
    ctx.rotate(angle);
    ctx.beginPath();
    ctx.ellipse(0, 0, petalRadiusX, petalRadiusY, 0, 0, Math.PI * 2);
    fillAndStroke();
    ctx.restore();
  }
  ctx.fillStyle = "#facc15";
  ctx.beginPath();
  ctx.arc(x, y, Math.min(width, height) * 0.12, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = oldFill;
}

function drawCloud(geometry) {
  const width = pw(geometry.width ?? 0.3);
  const height = ph(geometry.height ?? 0.2);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  ctx.beginPath();
  ctx.ellipse(x - width * 0.22, y + height * 0.08, width * 0.24, height * 0.28, 0, 0, Math.PI * 2);
  ctx.ellipse(x, y - height * 0.08, width * 0.3, height * 0.38, 0, 0, Math.PI * 2);
  ctx.ellipse(x + width * 0.24, y + height * 0.08, width * 0.25, height * 0.3, 0, 0, Math.PI * 2);
  ctx.rect(x - width * 0.36, y, width * 0.72, height * 0.28);
  fillAndStroke();
}

function drawSun(geometry) {
  const width = pw(geometry.width ?? 0.25);
  const height = ph(geometry.height ?? 0.25);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  const radius = Math.min(width, height) * 0.25;
  for (let index = 0; index < 12; index += 1) {
    const angle = (index / 12) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(x + Math.cos(angle) * radius * 1.35, y + Math.sin(angle) * radius * 1.35);
    ctx.lineTo(x + Math.cos(angle) * radius * 2.0, y + Math.sin(angle) * radius * 2.0);
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  fillAndStroke();
}

function drawTree(geometry) {
  const width = pw(geometry.width ?? 0.26);
  const height = ph(geometry.height ?? 0.32);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  const oldFill = ctx.fillStyle;
  ctx.fillStyle = "#92400e";
  ctx.fillRect(x - width * 0.08, y + height * 0.08, width * 0.16, height * 0.34);
  ctx.strokeRect(x - width * 0.08, y + height * 0.08, width * 0.16, height * 0.34);
  ctx.fillStyle = oldFill === "transparent" ? "#22c55e" : oldFill;
  ctx.beginPath();
  ctx.arc(x, y - height * 0.12, Math.min(width, height) * 0.32, 0, Math.PI * 2);
  fillAndStroke();
  ctx.fillStyle = oldFill;
}

function drawHouse(geometry) {
  const width = pw(geometry.width ?? 0.3);
  const height = ph(geometry.height ?? 0.26);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  const oldFill = ctx.fillStyle;
  ctx.beginPath();
  ctx.moveTo(x, y - height * 0.5);
  ctx.lineTo(x + width * 0.5, y - height * 0.1);
  ctx.lineTo(x - width * 0.5, y - height * 0.1);
  ctx.closePath();
  fillAndStroke();
  ctx.fillStyle = oldFill === "transparent" ? "#f97316" : oldFill;
  ctx.fillRect(x - width * 0.38, y - height * 0.1, width * 0.76, height * 0.55);
  ctx.strokeRect(x - width * 0.38, y - height * 0.1, width * 0.76, height * 0.55);
  ctx.fillStyle = "#92400e";
  ctx.fillRect(x - width * 0.08, y + height * 0.16, width * 0.16, height * 0.29);
  ctx.strokeRect(x - width * 0.08, y + height * 0.16, width * 0.16, height * 0.29);
  ctx.fillStyle = oldFill;
}

function drawMountain(geometry) {
  const width = pw(geometry.width ?? 0.34);
  const height = ph(geometry.height ?? 0.24);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  ctx.beginPath();
  ctx.moveTo(x - width * 0.5, y + height * 0.45);
  ctx.lineTo(x - width * 0.18, y - height * 0.45);
  ctx.lineTo(x + width * 0.12, y + height * 0.45);
  ctx.lineTo(x + width * 0.28, y - height * 0.28);
  ctx.lineTo(x + width * 0.5, y + height * 0.45);
  ctx.closePath();
  fillAndStroke();
}

function drawSmile(geometry) {
  const width = pw(geometry.width ?? 0.24);
  const height = ph(geometry.height ?? 0.24);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  const radius = Math.min(width, height) * 0.42;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  fillAndStroke();
  ctx.fillStyle = ctx.strokeStyle;
  ctx.beginPath();
  ctx.arc(x - radius * 0.35, y - radius * 0.22, Math.max(2, radius * 0.08), 0, Math.PI * 2);
  ctx.arc(x + radius * 0.35, y - radius * 0.22, Math.max(2, radius * 0.08), 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x, y + radius * 0.05, radius * 0.46, 0.18 * Math.PI, 0.82 * Math.PI);
  ctx.stroke();
}

function drawLightning(geometry) {
  const width = pw(geometry.width ?? 0.22);
  const height = ph(geometry.height ?? 0.28);
  const x = px(geometry.x ?? 0.5);
  const y = py(geometry.y ?? 0.5);
  ctx.beginPath();
  ctx.moveTo(x + width * 0.12, y - height * 0.5);
  ctx.lineTo(x - width * 0.28, y + height * 0.05);
  ctx.lineTo(x - width * 0.04, y + height * 0.05);
  ctx.lineTo(x - width * 0.16, y + height * 0.5);
  ctx.lineTo(x + width * 0.3, y - height * 0.12);
  ctx.lineTo(x + width * 0.06, y - height * 0.12);
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

function drawSelection(group) {
  const objects = Array.isArray(group) ? group : [group];
  const bounds = getGroupBounds(objects);
  ctx.save();
  ctx.strokeStyle = "#2f6fed";
  ctx.lineWidth = 2;
  ctx.setLineDash([7, 5]);
  ctx.strokeRect(bounds.x - 6, bounds.y - 6, bounds.width + 12, bounds.height + 12);
  ctx.restore();
}

function getGroupBounds(objects) {
  const bounds = objects.map((object) => getBounds(object));
  const left = Math.min(...bounds.map((item) => item.x));
  const top = Math.min(...bounds.map((item) => item.y));
  const right = Math.max(...bounds.map((item) => item.x + item.width));
  const bottom = Math.max(...bounds.map((item) => item.y + item.height));
  return {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top),
  };
}

function getBounds(object) {
  const geometry = object.geometry || {};
  if (object.type === "path") {
    const bounds = getPathBoundsNormalized(object.path || []);
    return {
      x: px(bounds.x),
      y: py(bounds.y),
      width: Math.max(1, pw(bounds.width)),
      height: Math.max(1, ph(bounds.height)),
    };
  }
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

function getPathBoundsNormalized(path) {
  const xs = [];
  const ys = [];
  for (const command of path) {
    for (const key of ["x", "x1", "x2"]) {
      if (typeof command[key] === "number") xs.push(command[key]);
    }
    for (const key of ["y", "y1", "y2"]) {
      if (typeof command[key] === "number") ys.push(command[key]);
    }
  }
  if (!xs.length || !ys.length) {
    return { x: 0.45, y: 0.45, width: 0.1, height: 0.1 };
  }
  const left = Math.min(...xs);
  const top = Math.min(...ys);
  const right = Math.max(...xs);
  const bottom = Math.max(...ys);
  return {
    x: left,
    y: top,
    width: Math.max(0.01, right - left),
    height: Math.max(0.01, bottom - top),
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
  objectCount.textContent = String(countGroups(state.objects));
  selectionCount.textContent = String(countGroups(getTargets("selected")));
}

function countGroups(objects) {
  return new Set(objects.map((object) => object.groupId || object.id)).size;
}

function updatePlanTelemetry(plan) {
  const operations = Array.isArray(plan.operations) ? plan.operations : [];
  const metadata = plan.metadata || {};
  const confidence = typeof plan.confidence === "number" ? `${Math.round(plan.confidence * 100)}%` : "--";
  const source = sourceLabel(plan.source, metadata);
  sourceText.textContent = source;
  confidenceText.textContent = confidence;
  operationCountText.textContent = String(operations.length);
  if (metadata.llm_latency_ms !== undefined) latencyText.textContent = `${metadata.llm_latency_ms} ms`;
  if (metadata.llm_model) modelText.textContent = metadata.llm_model;
}

function sourceLabel(source, metadata = {}) {
  if (metadata.llm_attempted && source === "llm") return "AI";
  if (metadata.llm_attempted) return "AI 兜底";
  if (source === "rule") return "本地规则";
  if (source === "repaired") return "修复";
  return source || "--";
}

function addLog(transcript, feedback, plan = {}) {
  const item = document.createElement("li");
  const title = document.createElement("strong");
  title.textContent = transcript;
  const body = document.createElement("span");
  body.textContent = feedback;
  const meta = document.createElement("small");
  const metadata = plan.metadata || {};
  const latency = metadata.llm_latency_ms !== undefined ? ` · ${metadata.llm_latency_ms} ms` : "";
  const confidence = typeof plan.confidence === "number" ? ` · ${Math.round(plan.confidence * 100)}%` : "";
  meta.textContent = `${sourceLabel(plan.source, metadata)}${latency}${confidence}`;
  item.append(title, body, meta);
  activityLog.prepend(item);
  while (activityLog.children.length > 20) {
    activityLog.removeChild(activityLog.lastChild);
  }
  historyCountText.textContent = String(activityLog.children.length);
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
    if (tryApplyCanvasSizeCommand(transcript)) continue;
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
          recent_object_ids: getRecentGroupIds(10),
        }),
      });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const errorBody = await response.json();
          if (errorBody.detail) detail = errorBody.detail;
        } catch {
          // Keep the status-only message when the response is not JSON.
        }
        throw new Error(detail);
      }
      const plan = await response.json();
      applyPlan(plan, transcript);
    } catch (error) {
      const message = `指令处理失败: ${error.message}`;
      addLog(transcript, message);
      setStatus("error", "处理失败");
    }
  }
  state.processing = false;
  if (!recognitionActive) scheduleListeningRestart();
  if (recognitionActive) setStatus("listening", "正在聆听");
}

function getRecentGroupIds(limit) {
  const ids = [];
  for (let index = state.objects.length - 1; index >= 0; index -= 1) {
    const groupId = state.objects[index].groupId || state.objects[index].id;
    if (!ids.includes(groupId)) ids.push(groupId);
    if (ids.length >= limit) break;
  }
  return ids.reverse();
}

function parseCanvasSizeCommand(transcript) {
  const text = transcript.replace(/\s+/g, "");
  if (!/(画布|尺寸|大小|宽|高|分辨率)/.test(text)) return null;

  let match = text.match(/(\d{3,4})\s*[xX×*乘]\s*(\d{3,4})/);
  if (!match) {
    match = text.match(/宽(?:度)?(?:设为|设置为|改成|改为|是|到)?(\d{3,4}).*高(?:度)?(?:设为|设置为|改成|改为|是|到)?(\d{3,4})/);
  }
  if (!match) {
    match = text.match(/高(?:度)?(?:设为|设置为|改成|改为|是|到)?(\d{3,4}).*宽(?:度)?(?:设为|设置为|改成|改为|是|到)?(\d{3,4})/);
    if (match) match = [match[0], match[2], match[1]];
  }
  if (!match) return null;

  const width = Math.max(MIN_CANVAS_SIZE, Math.min(MAX_CANVAS_SIZE, Number(match[1])));
  const height = Math.max(MIN_CANVAS_SIZE, Math.min(MAX_CANVAS_SIZE, Number(match[2])));
  return { width, height };
}

function tryApplyCanvasSizeCommand(transcript) {
  const size = parseCanvasSizeCommand(transcript);
  if (!size) return false;
  state.canvasSize = size;
  resizeCanvas();
  updateMetrics();
  const feedback = `画布尺寸已设置为 ${size.width} x ${size.height}`;
  confidenceText.textContent = "--";
  operationCountText.textContent = "0";
  addLog(transcript, feedback, {
    source: "rule",
    confidence: 1,
    operations: [],
    metadata: {},
  });
  setStatus(recognitionActive ? "listening" : "idle", recognitionActive ? "正在聆听" : "待命");
  return true;
}

function initTextTesting() {
  testCommandForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const command = testCommandInput.value.trim();
    if (!command) return;
    testCommandInput.value = "";
    await enqueueTranscript(command);
  });

  const params = new URLSearchParams(window.location.search);
  const testCommand = params.get("test");
  if (testCommand) {
    testCommandInput.value = testCommand;
    window.setTimeout(() => enqueueTranscript(testCommand), 250);
  }
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const health = await response.json();
    aiStatusText.textContent = health.llm_ready ? "已连接" : "未配置";
    modelText.textContent = health.llm_model || "--";
    if (!health.llm_ready) {
      sourceText.textContent = "AI 未配置";
    }
  } catch {
    aiStatusText.textContent = "离线";
    sourceText.textContent = "服务异常";
  }
}

function initVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setStatus("error", "当前浏览器不支持语音识别");
    return;
  }

  SpeechRecognitionCtor = SpeechRecognition;
  createRecognition();
  startListening();
}

function createRecognition() {
  if (!SpeechRecognitionCtor) return;

  recognition = new SpeechRecognitionCtor();
  recognition.lang = "zh-CN";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    recognitionActive = true;
    voiceRestarting = false;
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
    scheduleListeningRestart();
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

}

function startListening() {
  if (recognitionActive || voiceBlocked || state.processing) return;
  if (!recognition) createRecognition();
  if (!recognition) return;
  try {
    recognition.start();
  } catch {
    clearTimeout(restartTimer);
    recognition = null;
    restartTimer = setTimeout(() => startListening(), 1000);
  }
}

function scheduleListeningRestart() {
  clearTimeout(restartTimer);
  if (voiceBlocked || state.processing || voiceRestarting) return;
  voiceRestarting = true;
  recognition = null;
  restartTimer = setTimeout(() => {
    voiceRestarting = false;
    startListening();
  }, 600);
}

window.addEventListener("resize", resizeCanvas);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") startListening();
});

resizeCanvas();
updateMetrics();
loadHealth();
initTextTesting();
initVoice();

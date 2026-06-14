from __future__ import annotations

from backend.domain.models import (
    CommandPlan,
    DrawingOperation,
    DrawingStyle,
    OperationType,
)


class PlanValidator:
    """绘图计划校验器，负责过滤 AI 返回的非法动作。"""

    def validate(self, plan: CommandPlan) -> CommandPlan:
        """逐条检查操作，确保返回给前端的计划至少包含一个动作。"""
        operations: list[DrawingOperation] = []
        warnings = list(plan.warnings)

        for operation in plan.operations:
            checked, op_warnings = self._check_operation(operation)
            warnings.extend(op_warnings)
            if checked is not None:
                operations.append(checked)

        if not operations:
            # 所有动作都无效时保留一个 no_op，避免前端收到空计划。
            operations.append(
                DrawingOperation(
                    type=OperationType.NO_OP,
                    description="No valid operation after validation.",
                )
            )
            warnings.append("校验后没有可执行动作。")

        return plan.model_copy(
            update={
                "operations": operations,
                "warnings": warnings,
                "spoken_feedback": plan.spoken_feedback or "指令已处理。",
            }
        )

    def _check_operation(self, operation: DrawingOperation) -> tuple[DrawingOperation | None, list[str]]:
        """检查单条操作；缺少 AI 必填字段时返回 None 表示跳过。"""
        warnings: list[str] = []
        if operation.type in {OperationType.DRAW_SHAPE, OperationType.ADD_TEXT, OperationType.DRAW_PATH}:
            if operation.type == OperationType.DRAW_SHAPE and operation.shape is None:
                warnings.append("绘图动作缺少 shape，已跳过。")
                return None, warnings
            if operation.type == OperationType.DRAW_PATH and not operation.path:
                warnings.append("draw_path 缺少 path，已跳过。")
                return None, warnings
            if operation.type in {OperationType.DRAW_SHAPE, OperationType.ADD_TEXT} and operation.geometry is None:
                warnings.append(f"{operation.type.value} 缺少 geometry，已跳过。")
                return None, warnings
            # 绘制类动作必须带样式，没有就使用默认描边。
            operation = self._ensure_style(operation)

        if operation.type in {OperationType.MOVE, OperationType.RESIZE, OperationType.ROTATE}:
            # 变换类动作默认作用于当前选区。
            if operation.target is None:
                operation = operation.model_copy(update={"target": "selected"})

        if operation.type in {OperationType.SELECT, OperationType.DELETE} and operation.target is None:
            operation = operation.model_copy(update={"target": "selected"})

        if operation.type == OperationType.SET_CANVAS_SIZE and not operation.value:
            warnings.append("set_canvas_size 缺少 value，已跳过。")
            return None, warnings

        return operation, warnings

    def _ensure_style(self, operation: DrawingOperation) -> DrawingOperation:
        """补齐默认绘图样式。"""
        if operation.style is not None:
            return operation
        return operation.model_copy(update={"style": DrawingStyle()})

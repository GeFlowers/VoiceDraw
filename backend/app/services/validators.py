from __future__ import annotations

from backend.app.domain.models import (
    CommandPlan,
    DrawingOperation,
    DrawingStyle,
    Geometry,
    OperationType,
    ShapeType,
)


class PlanValidator:
    def validate(self, plan: CommandPlan) -> CommandPlan:
        operations: list[DrawingOperation] = []
        warnings = list(plan.warnings)

        for operation in plan.operations:
            repaired, op_warnings = self._repair_operation(operation)
            warnings.extend(op_warnings)
            if repaired is not None:
                operations.append(repaired)

        if not operations:
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

    def _repair_operation(self, operation: DrawingOperation) -> tuple[DrawingOperation | None, list[str]]:
        warnings: list[str] = []
        if operation.type in {OperationType.DRAW_SHAPE, OperationType.ADD_TEXT}:
            if operation.type == OperationType.DRAW_SHAPE and operation.shape is None:
                warnings.append("绘图动作缺少 shape，已跳过。")
                return None, warnings
            operation = self._ensure_geometry(operation, warnings)
            operation = self._ensure_style(operation)

        if operation.type in {OperationType.MOVE, OperationType.RESIZE, OperationType.ROTATE}:
            if operation.target is None:
                operation = operation.model_copy(update={"target": "selected"})

        if operation.type in {OperationType.SELECT, OperationType.DELETE} and operation.target is None:
            operation = operation.model_copy(update={"target": "selected"})

        return operation, warnings

    def _ensure_style(self, operation: DrawingOperation) -> DrawingOperation:
        if operation.style is not None:
            return operation
        return operation.model_copy(update={"style": DrawingStyle()})

    def _ensure_geometry(self, operation: DrawingOperation, warnings: list[str]) -> DrawingOperation:
        if operation.geometry is not None:
            return operation

        if operation.shape in {ShapeType.LINE, ShapeType.ARROW}:
            geometry = Geometry(x=0.2, y=0.5, x2=0.8, y2=0.5)
        elif operation.shape == ShapeType.CIRCLE:
            geometry = Geometry(x=0.5, y=0.5, radius=0.1)
        elif operation.shape == ShapeType.TEXT:
            geometry = Geometry(x=0.5, y=0.5, height=0.08)
        else:
            geometry = Geometry(x=0.5, y=0.5, width=0.25, height=0.18)
        warnings.append(f"{operation.type.value} 缺少 geometry，已使用默认位置。")
        return operation.model_copy(update={"geometry": geometry})

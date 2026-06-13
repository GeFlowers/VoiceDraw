from backend.app.domain.models import CommandPlan, DrawingOperation, OperationType, ShapeType
from backend.app.services.validators import PlanValidator


def test_validator_repairs_missing_geometry_and_style() -> None:
    plan = CommandPlan(
        operations=[
            DrawingOperation(
                type=OperationType.DRAW_SHAPE,
                shape=ShapeType.RECTANGLE,
            )
        ],
        confidence=0.7,
    )

    repaired = PlanValidator().validate(plan)

    assert repaired.operations[0].geometry is not None
    assert repaired.operations[0].style is not None
    assert repaired.warnings


def test_validator_skips_shape_less_draw_operation() -> None:
    plan = CommandPlan(
        operations=[DrawingOperation(type=OperationType.DRAW_SHAPE)],
        confidence=0.4,
    )

    repaired = PlanValidator().validate(plan)

    assert repaired.operations[0].type == OperationType.NO_OP

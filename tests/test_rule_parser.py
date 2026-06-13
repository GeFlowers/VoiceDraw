from backend.app.domain.models import CommandRequest, OperationType, ShapeType
from backend.app.services.rule_parser import RuleBasedParser


def parse(text: str):
    return RuleBasedParser().parse(CommandRequest(transcript=text))


def test_parse_compound_shape_command() -> None:
    plan = parse("画一个红色圆，然后在右边画蓝色矩形")

    assert plan.confidence >= 0.8
    assert [operation.shape for operation in plan.operations] == [
        ShapeType.CIRCLE,
        ShapeType.RECTANGLE,
    ]
    assert plan.operations[0].style.stroke == "#ef4444"
    assert plan.operations[1].geometry.x == 0.78


def test_line_anchor_order_uses_text_order() -> None:
    plan = parse("画一条从右下角到左上角的粗线")
    operation = plan.operations[0]

    assert operation.shape == ShapeType.LINE
    assert operation.geometry.x == 0.8
    assert operation.geometry.y == 0.78
    assert operation.geometry.x2 == 0.2
    assert operation.geometry.y2 == 0.22
    assert operation.style.line_width == 9.0


def test_canvas_control_commands() -> None:
    clear_plan = parse("清空画布")
    undo_plan = parse("撤销")

    assert clear_plan.operations[0].type == OperationType.CLEAR
    assert undo_plan.operations[0].type == OperationType.UNDO


def test_move_command_uses_selected_target_when_available() -> None:
    parser = RuleBasedParser()
    request = CommandRequest(transcript="向右移动一点", selected_ids=["obj_1"])

    plan = parser.parse(request)

    assert plan.operations[0].type == OperationType.MOVE
    assert plan.operations[0].target == "selected"
    assert plan.operations[0].delta.dx > 0


def test_scene_preset_decomposes_into_multiple_operations() -> None:
    plan = parse("画太阳和一棵树")

    assert len(plan.operations) >= 3
    assert all(operation.type == OperationType.DRAW_SHAPE for operation in plan.operations)


def test_text_command_extracts_content_and_position() -> None:
    plan = parse("在顶部写上标题 Voice Draw")
    operation = plan.operations[0]

    assert operation.type == OperationType.ADD_TEXT
    assert operation.text == "标题 voice draw"
    assert operation.geometry.y == 0.18

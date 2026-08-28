from libs.core.annotation_workflow import (
    AnnotationTool,
    AnnotationWorkflow,
    EscapeOutcome,
    PromptPolicy,
)


def test_navigation_preserves_class_and_tool_but_new_session_clears_them():
    workflow = AnnotationWorkflow()
    workflow.start_session()
    workflow.set_active_class('vehicle')
    workflow.set_tool(AnnotationTool.RECTANGLE)

    workflow.navigate()
    assert workflow.snapshot.active_class == 'vehicle'
    assert workflow.snapshot.active_tool is AnnotationTool.RECTANGLE

    workflow.start_session()
    assert workflow.snapshot.active_class is None
    assert workflow.snapshot.active_tool is AnnotationTool.SELECT


def test_escape_cancels_geometry_before_selecting_the_neutral_tool():
    workflow = AnnotationWorkflow(prompt_policy=PromptPolicy.REUSE_ACTIVE)
    workflow.set_tool(AnnotationTool.POLYGON)
    workflow.begin_provisional()

    assert workflow.escape() is EscapeOutcome.CANCEL_PROVISIONAL
    assert workflow.snapshot.active_tool is AnnotationTool.POLYGON
    assert workflow.escape() is EscapeOutcome.SELECT_TOOL
    assert workflow.snapshot.active_tool is AnnotationTool.SELECT

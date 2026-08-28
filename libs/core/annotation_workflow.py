from dataclasses import dataclass, replace
from enum import Enum


class AnnotationTool(str, Enum):
    SELECT = 'select'
    RECTANGLE = 'rectangle'
    POLYGON = 'polygon'
    SMART_BOX = 'smart_box'
    SMART_POINTS = 'smart_points'


class PromptPolicy(str, Enum):
    REUSE_ACTIVE = 'reuse_active'
    CONFIRM_EACH = 'confirm_each'


class EscapeOutcome(str, Enum):
    CANCEL_PROVISIONAL = 'cancel_provisional'
    SELECT_TOOL = 'select_tool'
    NOOP = 'noop'


@dataclass(frozen=True)
class WorkflowSnapshot:
    active_class: object = None
    prompt_policy: PromptPolicy = PromptPolicy.REUSE_ACTIVE
    active_tool: AnnotationTool = AnnotationTool.SELECT
    provisional: bool = False


class AnnotationWorkflow:
    def __init__(self, prompt_policy=PromptPolicy.REUSE_ACTIVE):
        self._state = WorkflowSnapshot(prompt_policy=PromptPolicy(prompt_policy))

    @property
    def snapshot(self):
        return self._state

    def start_session(self):
        self._state = WorkflowSnapshot(prompt_policy=self._state.prompt_policy)

    def navigate(self):
        return self._state

    def set_active_class(self, label):
        value = str(label).strip() or None
        self._state = replace(self._state, active_class=value)

    def set_prompt_policy(self, policy):
        self._state = replace(
            self._state, prompt_policy=PromptPolicy(policy))

    def set_tool(self, tool):
        self._state = replace(self._state, active_tool=AnnotationTool(tool))

    def begin_provisional(self):
        self._state = replace(self._state, provisional=True)

    def finish_provisional(self):
        self._state = replace(self._state, provisional=False)

    def escape(self):
        if self._state.provisional:
            self.finish_provisional()
            return EscapeOutcome.CANCEL_PROVISIONAL
        if self._state.active_tool is not AnnotationTool.SELECT:
            self.set_tool(AnnotationTool.SELECT)
            return EscapeOutcome.SELECT_TOOL
        return EscapeOutcome.NOOP

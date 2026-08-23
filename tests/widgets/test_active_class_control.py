from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from libs.widgets.activeClassControl import ActiveClassControl


_APP = QApplication.instance() or QApplication([])


def test_selecting_a_class_establishes_it_immediately():
    control = ActiveClassControl()
    control.set_choices(['vehicle', 'person'])
    spy = QSignalSpy(control.classSelected)

    control.combo.setCurrentText('vehicle')
    control.combo.lineEdit().returnPressed.emit()

    assert control.active_class() == 'vehicle'
    assert spy[-1] == ['vehicle']


def test_choices_do_not_imply_a_selection():
    control = ActiveClassControl()
    control.set_choices(['vehicle'])

    assert control.active_class() is None
    assert control.combo.placeholderText() == 'Choose a class'
    assert control.choices() == ('vehicle',)


def test_prompt_confirmation_emits_the_confirm_each_policy():
    control = ActiveClassControl()
    spy = QSignalSpy(control.policyChanged)

    control.confirm_each.setChecked(True)

    assert spy[-1] == ['confirm_each']


def test_placeholder_uses_the_editable_line_edit_when_combo_lacks_the_qt5_api():
    class LegacyLineEdit(object):
        def __init__(self):
            self.placeholder = None

        def setPlaceholderText(self, value):
            self.placeholder = value

    class LegacyCombo(object):
        def __init__(self):
            self.edit = LegacyLineEdit()

        def lineEdit(self):
            return self.edit

    combo = LegacyCombo()

    ActiveClassControl._set_placeholder_text(combo)

    assert combo.edit.placeholder == 'Choose a class'

"""Separately packaged fixture used to qualify the public plugin API."""

from labelimgplusplus.plugins import (
    CommandSpec,
    PluginCapability,
    PluginMetadata,
)


EXECUTIONS = 0
DEACTIVATIONS = 0


class FixturePlugin:
    metadata = PluginMetadata(
        id="org.labelimgpp.fixture",
        display_name="Packaged Fixture",
        version="1.0.0",
        api_major=1,
        capabilities=(PluginCapability.COMMANDS,),
        description="Verifies activation from a separately installed wheel.",
        homepage="https://example.invalid/labelimgpp-fixture",
    )

    def activate(self, context):
        context.settings.set("activated", True)
        context.commands.register(CommandSpec(
            id="execute",
            title="Execute Fixture",
            callback=self._execute,
            default_shortcut="Ctrl+Alt+F",
        ))

    def deactivate(self):
        global DEACTIVATIONS
        DEACTIVATIONS += 1

    @staticmethod
    def _execute():
        global EXECUTIONS
        EXECUTIONS += 1


def create_plugin():
    return FixturePlugin()

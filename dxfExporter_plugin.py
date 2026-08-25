"""Abaqus CAE plugin to export the currently displayed object in DXF format

Carl Osterwisch, July 2026
"""

from pathlib import Path
from abaqusGui import *

__version__ = "0.1.0"

class ExportForm(AFXForm):
    ID_OVERWRITE = AFXForm.ID_LAST

    def __init__(self, owner):
        AFXForm.__init__(self, owner) # Construct the base class.

        FXMAPFUNC(self, SEL_COMMAND, self.ID_OVERWRITE, ExportForm.onOverwrite)

        export = AFXGuiCommand(mode=self,
                method='export',
                objectName='dxfExporter',
                registerQuery=FALSE)

        self.fileNameKw = AFXStringKeyword(command=export,
                name="fileName",
                isRequired=TRUE)

    def getFirstDialog(self):
        return AFXFileSelectorDialog(
                self,
                "Save Display As...",
                self.fileNameKw,
                None,
                patterns="AutoCAD DXF (*.dxf)",
                )

    def doCustomChecks(self):
        """Add default suffix and check if file exists"""
        filePath = Path(self.fileNameKw.getValue())
        if not filePath.suffix:
            filePath = filePath.with_suffix(".dxf")
            self.fileNameKw.setValue(str(filePath))
        if filePath.exists():
            db = self.getCurrentDialog()
            showAFXWarningDialog(db,
                "File already exists.\n\nOK to overwrite?",
                AFXDialog.YES|AFXDialog.NO,
                self, self.ID_OVERWRITE)
            return False  # interrupt command execution
        return True

    def onOverwrite(self, sender, sel, ptr):
        """Process result of overwrite confirmation"""
        if sender.getPressedButtonId() == AFXDialog.ID_CLICKED_YES:
            self.issueCommands(writeToReplay=True, writeToJournal=True)
        return 1

###########################################################################
# Register plugin
###########################################################################
toolset = getAFXApp().getAFXMainWindow().getPluginToolset()

toolset.registerGuiMenuButton(
        buttonText='Tools|DXF Export...',
        object=ExportForm(toolset),
        kernelInitString='import dxfExporter  # {}'.format(__version__),
        author='Carl Osterwisch',
        version=__version__,
        helpUrl="https://github.com/costerwi/plugin-dxfExporter",
        description=__doc__,
        )

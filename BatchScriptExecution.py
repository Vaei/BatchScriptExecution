import maya.cmds as cmds
import maya.mel as mel
from enum import Enum
import os, platform, stat, sys, subprocess, tempfile


class BatchScriptExecutionStatics:
    window_name = "batchScriptExecutionUI"
    command_option_var = "batchScriptExecutionCommand"
    command_option_perforce_var = "batchScriptExecutionP4Config"
    command_option_path_var = "batchScriptExecutionDirectory"

class BatchScriptExecutionHelper:
    @staticmethod
    def open_directory(path):
        if not os.path.exists(path):
            cmds.warning("Directory does not exist:", path)
            return

        if sys.platform == 'win32':
            # Windows
            os.startfile(path)
        elif sys.platform == 'darwin':
            # macOS
            subprocess.run(['open', path])
        elif sys.platform == 'linux':
            # Linux
            subprocess.run(['xdg-open', path])
        else:
            print("Unsupported OS")

    @staticmethod
    def open_directory_at_file(file_path):
        if not os.path.exists(file_path):
            cmds.warning("Path does not exist: {}".format(file_path))
            return

        if os.path.isdir(file_path):
            path = file_path
        else:
            path = os.path.dirname(file_path)

        if sys.platform == 'win32':
            # Windows: Use explorer /select to open the folder and select the file
            if os.path.isdir(file_path):
                os.startfile(path)
            else:
                subprocess.run(['explorer', '/select,', os.path.normpath(file_path)])
        elif sys.platform == 'darwin':
            # macOS: Use open -R to reveal the file in Finder
            subprocess.run(['open', '-R', file_path])
        elif sys.platform == 'linux':
            # Linux: Use xdg-open to open the folder (no native support for selecting the file)
            subprocess.run(['xdg-open', path])
        else:
            print("Unsupported OS")

    @staticmethod
    def get_path():
        return cmds.optionVar(query=BatchScriptExecutionStatics.command_option_path_var)

    @staticmethod
    def get_p4config():
        return cmds.optionVar(query=BatchScriptExecutionStatics.command_option_perforce_var)

class FileStatus(Enum):
    does_not_exist = 1
    writable = 2
    read_only = 3
    skip = 4

class FileResult(Enum):
    success = 0
    failed = 1
    file_invalid = 2
    file_tampered = 3  # this occurs when files are changed during confirmation dialog and it gets missed
    file_missing = 4  # this occurs when files are deleted or moved during confirmation dialog and it gets missed
    file_not_found = 5
    file_read_only = 6
    file_skipped = 7

class PendingFile:
    path = None
    file_name = None
    status = None
    result = None
    warning = None

    skip_file = False  # set by BatchScriptExecutionAccessEntry

    def __init__(self, path, file_name = None):
        self.path = path
        self.file_name = file_name
        self.status = BatchScriptExecutionAccessEntry.check_file_status(self.path)

class BatchScriptExecutionEqualButton:
    def __init__(self, label, parent, command=None, height=0):
        if height == 0:
            self.button = cmds.button(label=label, p=parent, command=command)
        else:
            self.button = cmds.button(label=label, h=height, p=parent, command=command)

class BatchScriptExecutionFiveEqualButtons:
    def __init__(self, parent, button1_label, button2_label, button3_label, button4_label, button5_label,
                 button1_command, button2_command, button3_command, button4_command, button5_command, spacing=0, height=0):
        cmds.setParent(parent)
        self.layout = cmds.formLayout()

        # Create five buttons
        self.button1 = BatchScriptExecutionEqualButton(button1_label, self.layout, button1_command, height)
        self.button2 = BatchScriptExecutionEqualButton(button2_label, self.layout, button2_command, height)
        self.button3 = BatchScriptExecutionEqualButton(button3_label, self.layout, button3_command, height)
        self.button4 = BatchScriptExecutionEqualButton(button4_label, self.layout, button4_command, height)
        self.button5 = BatchScriptExecutionEqualButton(button5_label, self.layout, button5_command, height)

        # Define the form layout with appropriate attach forms and positions
        cmds.formLayout(self.layout, edit=True,
                        attachForm=[(self.button1.button, 'top', spacing),
                                    (self.button1.button, 'left', spacing),
                                    (self.button2.button, 'top', spacing),
                                    (self.button3.button, 'top', spacing),
                                    (self.button4.button, 'top', spacing),
                                    (self.button5.button, 'top', spacing),
                                    (self.button5.button, 'right', spacing)],  # Attach the right edge of button5
                        attachPosition=[(self.button1.button, 'right', spacing, 20),
                                        (self.button2.button, 'left', spacing, 20),
                                        (self.button2.button, 'right', spacing, 40),
                                        (self.button3.button, 'left', spacing, 40),
                                        (self.button3.button, 'right', spacing, 60),
                                        (self.button4.button, 'left', spacing, 60),
                                        (self.button4.button, 'right', spacing, 80),
                                        (self.button5.button, 'left', spacing, 80)])

class BatchScriptExecutionAccessEntry:
    """A single entry in the BatchScriptExecutionAccessHandler"""

    handler = None
    file = None
    status = None

    valid_color = [0.25, 0.5, 0.25]
    alt_valid_color = [0.25, 0.5, 0.5]
    invalid_color = [0.5, 0.25, 0.25]
    alt_invalid_color = [0.1, 0.1, 0.1]

    def __init__(self, handler, layout, file):
        self.handler = handler
        self.file = file
        if self.file.file_name is None:
            self.file.file_name = file.path.split("/")[-1]

        column_layout = cmds.columnLayout(adj=1, columnAlign="left", parent=layout)
        cmds.separator(h=4, style="none", p=column_layout)
        cmds.separator(h=1, p=column_layout)

        row_layout = cmds.rowLayout(nc=9, parent=column_layout)

        self.ready_text = cmds.text(l="", h=30, w=30, p=row_layout)  # tick-box

        cmds.separator(w=4, style="none", p=row_layout)

        self.file_text = cmds.text(l=file.file_name, h=30, w=480, p=row_layout)  # file name (.fbx)
        self.status_text = cmds.text(h=30, w=70, p=row_layout)

        cmds.separator(w=10, style="none", p=row_layout)

        self.checkout_button = cmds.button(l="Checkout", w=90, h=30, c=lambda unused: self.checkout_file(self), p=row_layout)
        self.writable_button = cmds.button(l="Make Writable", w=90, h=30, c=lambda unused: self.make_writable(self), p=row_layout)
        self.skip_button = cmds.button(l="Skip", w=90, h=30, c=self.skip_file, p=row_layout)
        self.refresh_button = cmds.button(l="Refresh", w=90, h=30, c=lambda unused: self.refresh(self), p=row_layout)

        cmds.separator(h=1, p=column_layout)

        self.refresh_ui()

    @staticmethod
    def has_perforce_installed():
        try:
            from P4 import P4, P4Exception
            return True
        except ImportError:
            return False

    def refresh_ui(self):
        status = self.file.status
        dont_skip = status is not FileStatus.skip
        cmds.text(self.file_text, e=1, en=dont_skip)
        cmds.text(self.ready_text, e=1, bgc=self.get_ready_color(status))
        cmds.text(self.status_text, e=1, l=self.get_status_text(status),
                                     bgc=self.get_status_color(status))

        cmds.button(self.skip_button, e=1, l="Skip" if dont_skip else "Don't Skip")

        read_only = status is FileStatus.read_only and dont_skip
        cmds.button(self.checkout_button, e=1, en=read_only)
        cmds.button(self.writable_button, e=1, en=read_only)
        cmds.button(self.refresh_button, e=1, en=dont_skip)

        if self.handler:
            self.handler.update_continue_button(self.handler)

    @staticmethod
    def check_file_status(path):
        # Check if the file exists
        if os.path.exists(path):
            # Check if the file is writable (not read-only)
            if os.access(path, os.W_OK):
                return FileStatus.writable
            else:
                return FileStatus.read_only
        else:
            return FileStatus.does_not_exist

    @staticmethod
    def check_directory_status(directory):
        # Check if the directory exists
        if not os.path.exists(directory):
            return False, "Directory does not exist."

        # Check if the path is a directory
        if not os.path.isdir(directory):
            return False, "Path exists but is not a directory."

        # Check if the directory can be written to
        try:
            # Attempt to create a temporary file within the directory
            testfile = tempfile.TemporaryFile(dir=directory)
            testfile.close()  # Close and remove the test file immediately
        except (OSError, IOError) as e:
            return False, f"Directory cannot be written to: {e}"

        # If all checks pass
        return True, "Directory exists, is valid, and writable."

    def read_p4config(self, config_path):
        settings = {}
        with open(config_path, 'r') as file:
            for line in file:
                if "=" in line:
                    key, value = line.strip().split('=', 1)
                    settings[key.strip()] = value.strip()
        return settings

    def checkout_file_perforce(self, path):
        if not self.has_perforce_installed():
            return False

        from P4 import P4, P4Exception

        has_p4config = cmds.optionVar(exists=BatchScriptExecutionStatics.command_option_perforce_var)
        p4config = cmds.optionVar(query=BatchScriptExecutionStatics.command_option_perforce_var) if has_p4config else ""
        if not p4config:
            cmds.confirmDialog(title="Checkout Failed", message=f"Perforce for Maya could not find a p4config file at {p4config}", button=["Dismiss"], defaultButton="Dismiss",
                               cancelButton="Dismiss", dismissString="Dismiss")
            return False

        config = self.read_p4config(p4config)

        p4 = P4()
        p4.port = config["P4PORT"]
        p4.client = config["P4CLIENT"]
        p4.user = config["P4USER"]

        print(f"Attempting to connect to Perforce on port {p4.port}, client {p4.client}, user {p4.user}")

        success = False

        try:
            p4.connect()
            print(f"Successfully connected to Perforce")
            p4.run("edit", path)
            print(f"Successfully checked out: {path}")
            success = True
        except P4Exception as e:
            error_str = f"Failed to check out: {path}. Error: {str(e)}"
            print(error_str)
            hint_str = "None"
            if "not on client." in str(e):
                hint_str = "The file does not exist in perforce, use 'Make Writable'."
            cmds.confirmDialog(title="Checkout Failed", message=error_str + "\n\nHint: " + hint_str + "\n\nAsk Jared or Cort for instructions (copy/paste this error from the Maya Script Editor)", button=["Dismiss"], defaultButton="Dismiss",
                               cancelButton="Dismiss", dismissString="Dismiss")
        finally:
            p4.disconnect()

        return success


    @staticmethod
    def checkout_file(self):
        if not self.has_perforce_installed():
            cmds.confirmDialog(title="Checkout Failed", message="Perforce for Maya not installed.\n\nAsk Jared or Cort for instructions", button=["Dismiss"], defaultButton="Dismiss",
                               cancelButton="Dismiss", dismissString="Dismiss")
            return
        if self.check_file_status(self.file.path) == FileStatus.read_only:
            self.checkout_file_perforce(self.file.path)
            self.refresh(self)
            self.handler.update_continue_button(self.handler)

    @staticmethod
    def is_unix():
        os_name = platform.system()
        if os_name == "Windows":
            return False
        if os_name == "Linux" or os_name == "Darwin":  # Darwin is macOS
            return True
        raise RuntimeError(f"OS for platform {os_name} cannot be determined.")

    @staticmethod
    def make_file_writable(path):
        if BatchScriptExecutionAccessEntry.is_unix():  # @todo Unix is untested!
            try:
                # Add write permission for owner, group, and others
                os.chmod(path, os.stat(path).st_mode | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
            except OSError as e:
                cmds.error("Error adding write permissions:", e)
        else:
            try:
                # Get current permissions
                file_stat = os.stat(path)
                # Remove read-only flag
                os.chmod(path, file_stat.st_mode | stat.S_IWRITE)
            except OSError as e:
                cmds.error("Error removing read-only attribute:", e)

    @staticmethod
    def make_writable(self):
        if self.check_file_status(self.file.path) == FileStatus.read_only:
            print("make writ")
            print(self.file.path)
            self.make_file_writable(self.file.path)
            print("make writ done")
            self.refresh(self)
            self.handler.update_continue_button(self.handler)

    @staticmethod
    def refresh(self):
        self.file.status = FileStatus.skip if self.file.status is FileStatus.skip else self.check_file_status(self.file.path)
        # print("refresh ", self.file, "   ", self.file.status)
        self.refresh_ui()

    def skip_file(*args):
        self = args[0]
        self.file.status = FileStatus.skip if self.file.status is not FileStatus.skip else self.check_file_status(self.file.path)
        self.refresh(self)
        self.handler.update_continue_button(self.handler)

    @staticmethod
    def get_ready_text(status):
        if status == FileStatus.read_only:
            return "Failed"
        elif status == FileStatus.writable:
            return "Ready"
        elif status == FileStatus.does_not_exist:
            return "Ready"

    @staticmethod
    def get_ready_color(status):
        if status == FileStatus.skip:
            return BatchScriptExecutionAccessEntry.alt_invalid_color
        elif status == FileStatus.read_only:
            return BatchScriptExecutionAccessEntry.invalid_color
        elif status == FileStatus.writable:
            return BatchScriptExecutionAccessEntry.valid_color
        elif status == FileStatus.does_not_exist:
            return BatchScriptExecutionAccessEntry.valid_color

    @staticmethod
    def get_status_text(status):
        if status == FileStatus.skip:
            return "Skip"
        elif status == FileStatus.read_only:
            return "Read-Only"
        elif status == FileStatus.writable:
            return "Replace"
        elif status == FileStatus.does_not_exist:
            return "New File"

    @staticmethod
    def get_status_color(status):
        if status == FileStatus.skip:
            return BatchScriptExecutionAccessEntry.alt_invalid_color
        elif status == FileStatus.read_only:
            return BatchScriptExecutionAccessEntry.invalid_color
        elif status == FileStatus.writable:
            return BatchScriptExecutionAccessEntry.alt_valid_color
        elif status == FileStatus.does_not_exist:
            return BatchScriptExecutionAccessEntry.valid_color

class BatchScriptExecutionAccessHandler:
    """Lists files and allows checking out or making writable or skipping"""

    files = {}  # Maya Scenes
    result = False  # False abort, True continue
    continue_button = None
    checkout_button = None

    def __init__(self, title, files):
        self.files = files

        # Process files
        if not self.files:
            return

        # Draw each file to screen
        cmds.layoutDialog(title=title, ui=self.spawn_ui)

    def spawn_ui(self):
        layout = cmds.setParent(q=True)
        scroll_layout = cmds.scrollLayout(verticalScrollBarAlwaysVisible=True, width=1000, height=400,
                                          verticalScrollBarThickness=16, childResizable=True, parent=layout)

        # Create entries for each file
        for scene, file in self.files.items():
            file.access_handler_entry = BatchScriptExecutionAccessEntry(self, scroll_layout, file)

        # Add continue & abort buttons
        buttons = BatchScriptExecutionFiveEqualButtons(
            layout, "Checkout All", "Refresh All", "Open Directory", "Continue", "Abort",
            self.press_checkout_button, self.press_refresh_button, self.press_open_directory_button, self.press_continue_button, self.press_abort_button, 4, 30)

        self.continue_button = buttons.button4.button
        self.checkout_button = buttons.button1.button
        cmds.button(self.continue_button, e=1, en=self.can_continue())

        # Attach the scrollLayout edges to the formLayout with some spacing
        cmds.formLayout(
            layout, edit=True,
            attachForm=[
                (scroll_layout, 'top', 0), (scroll_layout, 'left', 0), (scroll_layout, 'right', 0), (scroll_layout, 'bottom', 60),
                (buttons.layout, 'left', 0), (buttons.layout, 'right', 0), (buttons.layout, 'bottom', 10)
            ]
        )

    @staticmethod
    def update_continue_button(self):
        if self.continue_button:
            cmds.button(self.continue_button, e=1, en=self.can_continue())
        if self.checkout_button:
            cmds.button(self.checkout_button, e=1, en=not self.can_continue())

    def can_continue(self):
        for scene, file in self.files.items():
            if file.status == FileStatus.read_only:
                return False
        return True

    def press_checkout_button(*args):
        self = args[0]
        for scene, files in self.files.items():
            for file in files:
                file.access_handler_entry.checkout_file(file.access_handler_entry)
        self.press_refresh_button(args)

    def press_refresh_button(*args):
        self = args[0]
        for scene, files in self.files.items():
            for file in files:
                file.access_handler_entry.refresh(file.access_handler_entry)
        self.update_continue_button(self)

    @staticmethod
    def press_open_directory_button():
        path = BatchScriptExecutionHelper.get_path()
        BatchScriptExecutionHelper.open_directory(path)

    def press_continue_button(*args):
        self = args[0]
        if not self.can_continue():
            BatchScriptExecutionAccessHandler.update_continue_button(self)
            return
        self.result = True
        cmds.layoutDialog(dismiss="Close")

    def press_abort_button(*args):
        args[0].result = False
        cmds.layoutDialog(dismiss="Close")


class BatchScriptExecutionUI:
    last_command = ""

    def __init__(self):
        if cmds.window(BatchScriptExecutionStatics.window_name, exists=True):
            self.delete_ui()

        self.create_ui()

    def delete_ui(self):
        if cmds.window(BatchScriptExecutionStatics.window_name, exists=True):
            cmds.deleteUI(BatchScriptExecutionStatics.window_name, window=True)

    def create_ui(self):
        self.window = cmds.window(BatchScriptExecutionStatics.window_name, title="Batch Script Execution", sizeable=True, widthHeight=(400, 300))
        self.layout = cmds.formLayout("batchScriptExecutionLayout", parent=self.window)

        # Command type options (Python or MEL)
        command_type_radio = cmds.radioButtonGrp(
            p=self.layout,
            cal=[1, "left"],
            label="Command Type:",
            numberOfRadioButtons=2,
            labelArray2=["Python", "MEL"],
            select=1
        )

        # Multiline text field for editing the command
        has_command = cmds.optionVar(exists=BatchScriptExecutionStatics.command_option_var)
        saved_command = cmds.optionVar(query=BatchScriptExecutionStatics.command_option_var) if has_command else ""
        self.last_command = saved_command
        self.command_field = cmds.scrollField(p=self.layout, text=saved_command, wordWrap=True, height=200,
                                         changeCommand=lambda _: on_text_changed(),
                                         enterCommand=lambda _: on_text_changed(),
                                         keyPressCommand=lambda _: on_text_changed())

        has_command = self.last_command != ""

        # Save and Cancel buttons
        button_layout = cmds.formLayout("batchscript_button_layout", p=self.layout)
        self.save_button = cmds.button("batchscript_save", p=button_layout, width=150, label="Save Changes", enable=False, command=lambda _: save_changes())
        self.execute_button = cmds.button("batchscript_execute", p=button_layout, width=150, label="Execute", enable=has_command, command=lambda _: execute_script())
        self.cancel_button = cmds.button("batchscript_cancel", p=button_layout, width=150, label="Revert Changes", enable=False,
                                    command=lambda _: revert_changes())

        # Settings
        self.settings_layout = cmds.frameLayout(label="Settings", collapsable=False, collapse=False, p=self.layout)
        self.settings_prefix = cmds.textFieldGrp(label="Filter Prefix: ", text="", ann="Skip files with prefix", adj=2, cal=[1, "left"], p=self.settings_layout)
        self.settings_suffix = cmds.textFieldGrp(label="Filter Suffix: ", text="", ann="Skip files with suffix, excluding extension", adj=2, cal=[1, "left"], p=self.settings_layout)
        self.settings_filter = cmds.textFieldGrp(label="Filter String: ", text="", adj=2, ann="Skip files containing string, excluding extension", cal=[1, "left"], p=self.settings_layout)
        self.settings_file_type = cmds.textFieldGrp(label="File Type: ", text="mb,ma", adj=2, ann="Only process these file types", cal=[1, "left"], p=self.settings_layout)

        # Perforce config and directory
        config_layout = cmds.rowLayout(nc=3, adj=1, p=self.settings_layout)
        has_p4config = cmds.optionVar(exists=BatchScriptExecutionStatics.command_option_perforce_var)
        last_p4config = cmds.optionVar(query=BatchScriptExecutionStatics.command_option_perforce_var) if has_p4config else ""
        self.p4_config = cmds.textFieldGrp(
            label="P4 Config: ", text=last_p4config, adj=2,
            ann="Path to p4config file if using perforce. Must contain on separate lines, P4PORT=1.1.1.1:1666 P4USER=MyUser, P4CLIENT=MyWorkSpace",
            cal=[1, "left"], p=config_layout, changeCommand=lambda _: on_p4_config_changed())
        cmds.symbolButton(image="browseFolder.png", w=20, h=20, c=lambda unused: browse_for_p4config(), p=config_layout)
        cmds.symbolButton(image="fileOpen.png", w=20, h=20, c=lambda unused: BatchScriptExecutionHelper.open_directory_at_file(BatchScriptExecutionHelper.get_p4config()), p=config_layout)

        # Directory path
        path_layout = cmds.rowLayout(nc=3, adj=1, p=self.settings_layout)
        has_path = cmds.optionVar(exists=BatchScriptExecutionStatics.command_option_path_var)
        last_path = cmds.optionVar(query=BatchScriptExecutionStatics.command_option_path_var) if has_path else ""
        self.path = cmds.textFieldGrp(
            label="Directory: ", text=last_path, adj=2,
            ann="Path to directory containing files to be processed",
            cal=[1, "left"], p=path_layout, changeCommand=lambda _: on_path_changed())
        cmds.symbolButton(image="browseFolder.png", w=20, h=20, c=lambda unused: browse_for_path(), p=path_layout)
        cmds.symbolButton(image="fileOpen.png", w=20, h=20, c=lambda unused: BatchScriptExecutionHelper.open_directory(BatchScriptExecutionHelper.get_path()), p=path_layout)

        self.recursion_depth = cmds.intFieldGrp(value1=0, label="Recursion Depth", ann="Depth of recursion into subdirectories", cal=[1, "left"], adj=0, p=self.settings_layout)
        self.save_checkbox = cmds.checkBox(label="Save File After Script Execution", v=True, p=self.settings_layout)

        # Attach elements
        cmds.formLayout(
            self.layout, edit=True,
            attachForm=[
                (command_type_radio, "top", 10), (command_type_radio, "left", 10), (command_type_radio, "right", 10),
                (self.command_field, "left", 10), (self.command_field, "right", 10), (self.command_field, "bottom", 300),
                (button_layout, "left", 10), (button_layout, "right", 10),
                (self.settings_layout, "left", 10), (self.settings_layout, "right", 10),
            ],
            attachControl=[
                (self.command_field, "top", 10, command_type_radio),
                (self.settings_layout, "top", 10, self.command_field),
                (button_layout, "top", 10, self.settings_layout),
            ],
        )

        cmds.formLayout(
            button_layout, edit=True,
            attachForm=[
                (self.save_button, "left", 0),
                (self.execute_button, "left", 150), (self.execute_button, "right", 150),
                (self.cancel_button, "right", 0),
            ]
        )

        cmds.showWindow(self.window)

        def on_path_changed():
            cmds.optionVar(stringValue=(BatchScriptExecutionStatics.command_option_path_var, cmds.textFieldGrp(self.path, query=True, text=True)))

        def browse_for_path():
            path = cmds.fileDialog2(fileMode=3, caption="Select directory", okCaption="Select")
            if path:
                cmds.textFieldGrp(self.path, edit=True, text=path[0])
                cmds.optionVar(stringValue=(BatchScriptExecutionStatics.command_option_path_var, path[0]))

        def on_p4_config_changed():
            cmds.optionVar(stringValue=(BatchScriptExecutionStatics.command_option_perforce_var, cmds.textFieldGrp(self.p4_config, query=True, text=True)))

        def browse_for_p4config():
            path = cmds.fileDialog2(fileMode=1, caption="Select p4config file", okCaption="Select")
            if path:
                cmds.textFieldGrp(self.p4_config, edit=True, text=path[0])
                cmds.optionVar(stringValue=(BatchScriptExecutionStatics.command_option_perforce_var, path[0]))

        def has_pending_changes():
            return get_command() != self.last_command

        def get_command():
            return cmds.scrollField(self.command_field, query=True, text=True)

        def update_button_states():
            if not cmds.layout(self.layout, exists=True):
                return

            if not cmds.scrollField(self.command_field, exists=True):
                return

            try:
                cmds.button(self.save_button, edit=True, enable=has_pending_changes())
                cmds.button(self.cancel_button, edit=True, enable=has_pending_changes())
                cmds.button(self.execute_button, edit=True, enable=get_command() != "")
            except RuntimeError as e:
                print(f"Error updating buttons: {e}")

        def on_text_changed():
            cmds.evalDeferred(lambda: update_button_states())

        def save_changes():
            new_command = get_command()
            self.last_command = new_command
            cmds.optionVar(stringValue=(BatchScriptExecutionStatics.command_option_var, new_command))
            cmds.evalDeferred(lambda: update_button_states())

        def revert_changes():
            cmds.scrollField(self.command_field, edit=True, text=self.last_command)
            cmds.evalDeferred(lambda: on_text_changed())

        def error_dialog(reason, context):
            cmds.confirmDialog(title=context + " Failed", message=reason, button=["Dismiss"], defaultButton="Dismiss",
                               cancelButton="Dismiss", dismissString="Dismiss")

        def do_gather_maya_files(directory, recursion_depth):
            """
            Recursively searches for Maya files (.mb and .ma) in the given directory up to the specified depth.

            Parameters:
            - directory (str): The path to the directory where the search should begin.
            - depth (int): The maximum depth of recursion. A depth of 0 means only the current directory.

            Returns:
            - list: A list of paths to Maya files found within the specified depth.
            """
            maya_files = []
            if recursion_depth < 0:
                return maya_files  # Return an empty list if depth is negative

            # Process all entries in the current directory
            for entry in os.scandir(directory):
                if entry.is_file() and (entry.name.endswith('.mb') or entry.name.endswith('.ma')):
                    normalized_path = os.path.normpath(entry.path).replace('\\',
                                                                           '/')  # We don't want a back-slash on windows
                    maya_files.append(normalized_path)  # Add file to list if it's a Maya file

            if recursion_depth > 0:
                # Recurse into subdirectories if depth is greater than 0
                for entry in os.scandir(directory):
                    if entry.is_dir():  # Check if the entry is a directory
                        # Recursively search in the subdirectory with decremented depth
                        normalized_path = os.path.normpath(entry.path).replace('\\',
                                                                               '/')  # We don't want a back-slash on windows
                        maya_files.extend(do_gather_maya_files(normalized_path, recursion_depth - 1))

            return maya_files

        def gather_maya_files(context):
            directory = BatchScriptExecutionHelper.get_path()
            if directory is None or directory == "" or len(directory) == 0:
                error_dialog("Export directory not specified", context)
                return None, False

            dir_valid, dir_reason = BatchScriptExecutionAccessEntry.check_directory_status(directory)
            if not dir_valid:
                error_dialog(dir_reason, context)
                return None, False

            recursion_depth = cmds.intFieldGrp(self.recursion_depth, query=True, value1=True)
            maya_files = do_gather_maya_files(directory, recursion_depth)
            # print(f"gather {len(maya_files)} files, ", recursion_depth, " : ", maya_files)
            return maya_files, True

        def execute_script():
            if has_pending_changes():
                result = cmds.confirmDialog(
                    title="Unsaved Changes",
                    message="You have unsaved changes to your current script. Would you like to save them before"
                            " executing the script?",
                    button=["Yes", "No", "Cancel"])
                if result == "Yes":
                    save_changes()
                elif result == "Cancel":
                    return

            command_type = "python" if cmds.radioButtonGrp(command_type_radio, query=True, select=True) == 1 else "mel"
            command = cmds.optionVar(query=BatchScriptExecutionStatics.command_option_var)

            context = "Batch Execute Script"
            maya_files, valid_directory = gather_maya_files(context) or []
            if not valid_directory:
                return
            if len(maya_files) == 0:
                cmds.confirmDialog(title=context + " Failed", message="Directory is empty", button=["Dismiss"],
                                   defaultButton="Dismiss",
                                   cancelButton="Dismiss", dismissString="Dismiss")
                return

            # Filter files
            prefix = cmds.textFieldGrp(self.settings_prefix, query=True, text=True)
            suffix = cmds.textFieldGrp(self.settings_suffix, query=True, text=True)
            filter_string = cmds.textFieldGrp(self.settings_filter, query=True, text=True)
            file_type = cmds.textFieldGrp(self.settings_file_type, query=True, text=True)
            if file_type:
                file_type = file_type.replace(" ", "")  # Trim whitespace
                file_type = file_type.split(',')

            filtered_files = []
            removed_files = []
            for file in maya_files:
                file_name = os.path.basename(file)
                file_extension = file_name.split(".")[-1]
                file_name = file_name.split(".")[0]
                # print(f"file_name: {file_name}, has prefix: {prefix and file_name.startswith(prefix)}, has suffix: {suffix and file_name.endswith(suffix)}, has filter: {filter_string and filter_string in file_name}, has type: {file_name.endswith(tuple(file_type))}")
                if prefix and file_name.startswith(prefix):
                    removed_files.append(file)
                    continue
                if suffix and file_name.endswith(suffix):
                    removed_files.append(file)
                    continue
                if filter_string and filter_string in file_name:
                    continue
                if file_type and file_extension not in file_type:
                    continue
                filtered_files.append(file)

            maya_files = filtered_files
            # print(f"filtered files: {removed_files}")

            if len(maya_files) == 0:
                cmds.confirmDialog(title=context + " Failed", message="No files to process after filtering", button=["Dismiss"],
                                   defaultButton="Dismiss",
                                   cancelButton="Dismiss", dismissString="Dismiss")
                return

            # Confirm that the user wants to proceed if there are more than a few files
            result = cmds.confirmDialog(
                title='Confirm Batch Script Execution',
                message=f"Continue script execution for {len(maya_files)} files?\n\nThis process can potentially take a long time, because every file must be opened.",
                button=['Continue', 'Abort'],
                defaultButton='Continue',
                cancelButton='Abort',
                dismissString='Abort'
            )
            if result == 'Abort':
                return

            wants_save = cmds.checkBox(self.save_checkbox, query=True, value=True)

            pending_files = {}
            for file_path in maya_files:
                    pending_files[file_path] = PendingFile(file_path)

            # Build dict for exporting
            handler = BatchScriptExecutionAccessHandler("Confirm File List for Script Batch Execution", pending_files)
            if not handler.result:
                cmds.warning("Process aborted by the user.")
                return

            print(f"Executing script on {len(pending_files)} files")

            for file, pending_file in handler.files.items():
                # --STATUS--
                # does_not_exist = 1
                # writable = 2
                # read_only = 3
                # skip = 4
                print(f"pending file: {pending_file.status}")

                # File must be writable, cannot be a new file either
                if pending_file.status != FileStatus.writable:
                    if pending_file.status == FileStatus.skip:
                        pending_file.result = FileResult.file_skipped
                    elif pending_file.status == FileStatus.does_not_exist:
                        pending_file.result = FileResult.file_not_found
                    elif pending_file.status == FileStatus.read_only:
                        pending_file.result = FileResult.file_read_only
                    pending_file.warning = f"File could not be processed due to file state: {pending_file.status}"
                    print(f"File could not be processed due to file state: {pending_file.status}")
                    continue

                # Ensure the file hasn't become missing or read-only (i.e. something changed during validation dialog)
                status = BatchScriptExecutionAccessEntry.check_file_status(file)
                if status != FileStatus.writable:
                    # File has been tampered with and wasn't reflected in the confirmation dialog
                    tampered_missing = not os.path.exists(file)
                    pending_file.result = FileResult.file_missing if tampered_missing else FileResult.file_tampered
                    print(f"File has been tampered with and wasn't reflected in the confirmation dialog")
                    continue

                # Now we can open the file
                print(f"[ BatchScriptExecution ] Opening >>> {file}")
                cmds.file(file, open=True, force=True)

                # Then execute the script
                if command_type == "python":
                    exec(command, globals(), locals())
                else:
                    mel.eval(command)

                # Save the file if the user wants
                if wants_save:
                    cmds.file(save=True, force=True)

            # Close the final scene without saving
            cmds.file(new=True, force=True)

            # Show the user the results
            cmds.confirmDialog(title=context + " Results", message="Script execution complete.", button=["Dismiss"], defaultButton="Dismiss",
                               cancelButton="Dismiss", dismissString="Dismiss")

if __name__ == '__main__':
    # Dev only helper for reopening the window each time the script runs
    BatchScriptExecutionUI()

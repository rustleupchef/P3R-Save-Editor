import sys
import os
from simple_term_menu import TerminalMenu
from prompt_toolkit.shortcuts import input_dialog, message_dialog
from prompt_toolkit.validation import Validator, ValidationError

class DirectoryValidator(Validator):
    def validate(self, document):
        path = os.path.expanduser(document.text.strip())
        if not path:
            raise ValidationError(message="Path cannot be empty.")
        if not os.path.isdir(path):
            raise ValidationError(message="That path is not a valid directory.")

def grabPath():
    title = "P3R Save Editor"
    while True:
        result = input_dialog(
            title=title,
            text="Enter the folder containing your save files:",
            validator=DirectoryValidator(),
        ).run()

        if result is None:
            print("User chose to not answer")
            sys.exit(0)

        path = os.path.expanduser(result.strip())
        if os.path.isdir(path):
            return path

        message_dialog(
            title=title,
            text=f"Invalid path:\n{path}\n\nPlease try again.",
        ).run()


def selectOption(path):
    files = [
        file for file in os.listdir(path)
        if os.path.isfile(os.path.join(path, file))
    ]

    if not files:
        print("ERROR: There are no files within this directory")
        sys.exit(1)

    menu = TerminalMenu(files, title="Select the Desired Save")
    return menu.show()


def main(arguments = []):

    path = arguments[0] if len(arguments) > 0 and os.path.isdir(arguments[0]) else grabPath()
    option = arguments[1] if len(arguments) > 1 else selectOption(path)
    
    file_path = os.path.join(path, option)

if __name__ == "__main__":
    main(sys.argv[1:])
from ntpath import isfile
import sys
import os
import shutil
from typing import Optional
from simple_term_menu import TerminalMenu
from prompt_toolkit.shortcuts import input_dialog, message_dialog
from prompt_toolkit.validation import Validator, ValidationError

def encryptedToGVAS(file_path, output_file) -> Optional[bytes]:
    SAVE_KEY = b"ae5zeitaix1joowooNgie3fahP5Ohph"
    KEY_LEN = len(SAVE_KEY)
    
    ENCRYPT_GVAS_MAGIC = 0x0B650015
    DECRYPT_GVAS_MAGIC = 0x53415647

    try:
        with open(file_path, "rb") as f:
            save_data = f.read()
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        return None

    filesize = len(save_data)
    if filesize < 4:
        print("Error: File is too small to be a valid save file.")
        return None

    file_magic = int.from_bytes(save_data[:4], byteorder="little")
    
    if file_magic == ENCRYPT_GVAS_MAGIC:
        print(f"Detected encrypted save file (0x{file_magic:08x}). Decrypting...")
        out_data = bytearray(filesize)
        
        for i in range(filesize):
            b_var1 = (save_data[i] ^ SAVE_KEY[i % KEY_LEN]) & 0xFF
            out_data[i] = (((b_var1 >> 4) & 3) | ((b_var1 & 3) << 4) | (b_var1 & 0xCC)) & 0xFF
            
    elif file_magic == DECRYPT_GVAS_MAGIC:
        print(f"Detected decrypted save file (0x{file_magic:08x}). Encrypting...")
        out_data = bytearray(filesize)
        
        for i in range(filesize):
            temp = (((save_data[i] >> 4) & 3) | ((save_data[i] & 3) << 4) | (save_data[i] & 0xCC)) & 0xFF
            out_data[i] = (temp ^ SAVE_KEY[i % KEY_LEN]) & 0xFF
    else:
        print(f"Error: Unknown save file magic (0x{file_magic:08x}).")
        return None

    try:
        processed_bytes = bytes(out_data)
        with open(output_file, "wb") as f:
            f.write(processed_bytes)
        print(f"Successfully wrote {len(processed_bytes)} bytes to '{output_file}'")
        return processed_bytes
    except Exception as e:
        print(f"Error writing output file: {e}")
        return None

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
    return files[menu.show()]

def creatDirs(*paths):
    for path in paths:
        if not os.path.exists(path):
            os.mkdir(path)

def placeFiles(filePath, *paths):
    for path in paths:
        shutil.copy(filePath, path)

def main(arguments = []):

    path = arguments[0] if len(arguments) > 0 and os.path.isdir(arguments[0]) else grabPath()
    option = arguments[1] if len(arguments) > 1 else selectOption(path)

    filePath = os.path.join(path, option)

    BACKUP_FOLDER = "backups/"
    WORKING_FOLDER = "working/"
    creatDirs(BACKUP_FOLDER, WORKING_FOLDER)
    placeFiles(filePath, WORKING_FOLDER, BACKUP_FOLDER)

    filePath = os.path.join(WORKING_FOLDER, option)
    encryptedToGVAS(filePath, f"{filePath}.data")

if __name__ == "__main__":
    main(sys.argv[1:])
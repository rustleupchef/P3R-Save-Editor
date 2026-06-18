import sys
import os
import shutil
import json
from typing import Optional
from wasmtime import Engine, Store, Module, Linker, FuncType, ValType, Func
from simple_term_menu import TerminalMenu
from prompt_toolkit.shortcuts import input_dialog, message_dialog
from prompt_toolkit.validation import Validator, ValidationError

engine = Engine()
store = Store(engine)
wasm_path = os.path.join("uesave", "uesave_wasm_bg.wasm")
module = Module.from_file(engine, wasm_path)
linker = Linker(engine)
linker.define_wasi()
type_new = FuncType([], [ValType.externref()])
linker.define(store, "./uesave_wasm_bg.js", "__wbg_new_227d7c05414eb861", Func(store, type_new, lambda: None))
type_stack = FuncType([ValType.i32(), ValType.externref()], [])
linker.define(store, "./uesave_wasm_bg.js", "__wbg_stack_3b0d974bbf31e44f", Func(store, type_stack, lambda a, b: None))
type_drop = FuncType([ValType.i32()], [])
linker.define(store, "./uesave_wasm_bg.js", "__wbindgen_object_drop_contents", Func(store, type_drop, lambda a: None))
type_error = FuncType([ValType.i32(), ValType.i32()], [])
linker.define(store, "./uesave_wasm_bg.js", "__wbg_error_a6fa202b58aa1cd3", Func(store, type_error, lambda a, b: None))
type_init_table = FuncType([], [])
linker.define(store, "./uesave_wasm_bg.js", "__wbindgen_init_externref_table", Func(store, type_init_table, lambda: None))
type_cast = FuncType([ValType.i32(), ValType.i32()], [ValType.externref()])
linker.define(store, "./uesave_wasm_bg.js", "__wbindgen_cast_0000000000000001", Func(store, type_cast, lambda a, b: None))
instance = linker.instantiate(store, module)
memory = instance.exports(store)["memory"]
allocate_func = instance.exports(store).get("__wbindgen_malloc")
free_func = instance.exports(store).get("__wbindgen_free")

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

def gvasToJson(file_path, output_file):
    gvas_to_json_func = instance.exports(store).get("sav_to_json")

    with open(file_path, "rb") as file:
        gvas_bytes = file.read()
    
    size = len(gvas_bytes)
    ptr = allocate_func(store, size, 1)

    try:
        memory.write(store, gvas_bytes, ptr)
        result = gvas_to_json_func(store, ptr, size)
        
        if isinstance(result, list) or isinstance(result, tuple):
            json_data_ptr = result[0]
            json_data_len = result[1]
        elif hasattr(result, "value"):
            json_data_ptr = result.value
            json_data_len = size * 2
        else:
            json_data_ptr = int(result)
            length_bytes = memory.read(store, json_data_ptr + 4, json_data_ptr + 8)
            json_data_len = int.from_bytes(length_bytes, byteorder='little')
            
            ptr_bytes = memory.read(store, json_data_ptr, json_data_ptr + 4)
            json_data_ptr = int.from_bytes(ptr_bytes, byteorder='little')

        raw_json_bytes = memory.read(store, json_data_ptr, json_data_ptr + json_data_len)
        json_data = raw_json_bytes.decode("utf-8")

        free_func(store, json_data_ptr, json_data_len, 1)

        with open(output_file, "w", encoding="utf-8") as file:
            file.write(json_data)
            
        return json_data
        
    except Exception as e:
        print(f"Error parsing WebAssembly return configuration: {e}")
        raise e
    finally:
        try:
            free_func(store, ptr, size, 1)
        except Exception:
            pass

def jsonToGvas(file_path, output_file):
    json_to_gvas_func = instance.exports(store).get("json_to_sav")

    with open(file_path, "r", encoding="utf-8") as file:
        json_str = file.read()
    
    json_bytes = json_str.encode("utf-8")
    size = len(json_bytes)
    ptr = allocate_func(store, size, 1)

    try:
        memory.write(store, json_bytes, ptr)
        
        result = json_to_gvas_func(store, ptr, size)
        
        if isinstance(result, list) or isinstance(result, tuple):
            gvas_data_ptr = result[0]
            gvas_data_len = result[1]
        elif hasattr(result, "value"): 
            gvas_data_ptr = result.value
            gvas_data_len = size * 2
        else:
            gvas_data_ptr = int(result)
            length_bytes = memory.read(store, gvas_data_ptr + 4, gvas_data_ptr + 8)
            gvas_data_len = int.from_bytes(length_bytes, byteorder='little')
            
            ptr_bytes = memory.read(store, gvas_data_ptr, gvas_data_ptr + 4)
            gvas_data_ptr = int.from_bytes(ptr_bytes, byteorder='little')

        gvas_bytes = memory.read(store, gvas_data_ptr, gvas_data_ptr + gvas_data_len)

        free_func(store, gvas_data_ptr, gvas_data_len, 1)

        with open(output_file, "wb") as file:
            file.write(gvas_bytes)
            
        print(f"Successfully repacked {len(gvas_bytes)} bytes into '{output_file}'")
        return gvas_bytes
        
    except Exception as e:
        print(f"Error packing JSON data to WebAssembly format: {e}")
        raise e
    finally:
        try:
            free_func(store, ptr, size, 1)
        except Exception:
            pass

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

# TODO: Implement a assisted edit feature
def assistedEdit(file_path):
    pass

def edit(file_path):
    options = ["assisted", "manually"]
    menu = TerminalMenu(
        options,
        title="Select Your Desired Editing Mode"
    )
    manual = bool(menu.show())

    if not manual:
        assistedEdit(file_path)
        return
    
    menu = TerminalMenu(
        ["Confirm"],
        title = "Press the Confirm Option When You Are Finished Editing"
    )
    menu.show()

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
    gvasToJson(f"{filePath}.data", f"{filePath}.json")
    edit(f"{filePath}.json")
    jsonToGvas(f"{filePath}.json", f"{filePath}.data")
    encryptedToGVAS(f"{filePath}.data", filePath)

if __name__ == "__main__":
    main(sys.argv[1:])
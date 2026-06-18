## About
This is another Persona 3 Reload Save Editor. I attempted to differe this project from other editors by attempting to make it as simply and as clean as possible to setup. The project only requires an installation of python and pip to run, everything else is packaged inside the project. I was tired of all the editors being very scattered but also having terrible interactive layers to use the application.

## Usage
Before starting, make sure to install the depedencies

*** Note that it may be useful to make a virutal environment ***
```bash
pip install -r requirements.txt
```
This installs all the packages that are nessecary for the project.

To run the program enter:
```bash
python main.py
```

Once into to boot you will be hit with a couple steps:
 - Enter in the path of the folder that you will be pulling from
 - Then navigate the terminal menu to select which file from the folder you desire to edit
 - Then you wil get two options for your editing mode
    - Assisted Mode: This will guide you through the process to ensure you don't make mistakes (This has not been implemented yet)
    - Manual Mode: This will prompt another screen asking you to hit enter when you are ready. If you do this simply edit the json as you please and hit enter when you feel as though you are done

And after all of that, you will be finished with the process.

## Files

The folder structure is as so

 - backups/
    - This folder is where the program deposits the backups of the saves you are going to edit; refer back to this folder if something goes wrong
 - uesave/
    - This contains the web assembly compiled code for the gvas to json conversion; this allows the software to have one set of compiled files for nearly every os
 - working/
    - This contains all the generated files during the runtime of the code. The final product will also be deposited in this folder with the file extension .sav at the every end (Note that other files will have .sav in the name but none accept the product file will have it at the very end)
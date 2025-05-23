# SentientOS API Launcher

This repository contains a Python script that starts the various services used by the SentientOS project. It mirrors the behaviour of the Windows batch file used previously.

## Usage

Run the script with Python 3:

```bash
python start_services.py
```

On Windows, the script attempts to open each service in a separate command window, similar to the original batch file. On other platforms, the processes run in the background.

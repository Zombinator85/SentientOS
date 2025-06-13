#!/bin/bash
# Calls cathedral_launcher.py and logs output to launch_all_final.log

LOGFILE="$(dirname "$0")/launch_all_final.log"

echo "$(date) === Cathedral Launch Started ===" >> "$LOGFILE"
python cathedral_launcher.py >> "$LOGFILE" 2>&1
ret=$?
if [ $ret -ne 0 ]; then
  echo "$(date) ERROR: cathedral_launcher.py failed." >> "$LOGFILE"
  exit $ret
fi

echo "$(date) Cathedral launch complete." >> "$LOGFILE"

"""
Zabbix Metrics Extractor
Desktop application for automated extraction of visual metrics from Zabbix API.

Author: Generated with AI assistance
Compatible with PyInstaller for .exe generation
"""

import sys
import os

# Ensure proper path resolution for PyInstaller
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    application_path = os.path.dirname(sys.executable)
else:
    # Running as script
    application_path = os.path.dirname(os.path.abspath(__file__))

# Add application path to sys.path
sys.path.insert(0, application_path)

# Import and run the application
from gui import main

if __name__ == "__main__":
    main()

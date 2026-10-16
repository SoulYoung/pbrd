"""Use an actual C preprocessor to inspect macro-expanded configuration records."""
from pathlib import Path
import os,shutil,subprocess

def preprocess(path):
    compiler=os.environ.get('PBRD_C_PREPROCESSOR') or shutil.which('armcc') or shutil.which('clang') or shutil.which('gcc')
    if not compiler and Path('D:/Keil/ARM/ARMCC/bin/armcc.exe').is_file():compiler='D:/Keil/ARM/ARMCC/bin/armcc.exe'
    if not compiler:raise RuntimeError('Set PBRD_C_PREPROCESSOR to armcc, clang or gcc for macro verification')
    return subprocess.run([compiler,'-E',str(path)],capture_output=True,check=True).stdout.decode('utf-8-sig')

"""Build a self-contained Windows executable with declared resources."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

root=Path(__file__).resolve().parent
output=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else root/'dist'
output.mkdir(parents=True,exist_ok=True)
integration=root/'resources'/'integration'
integration.mkdir(parents=True,exist_ok=True)
(integration/'editing_copilot').mkdir(exist_ok=True)
for name in ('__init__.py','resolve.py'):
    shutil.copy2(root/'src'/'editing_copilot'/name,integration/'editing_copilot'/name)
shutil.copy2(root/'integrations'/'resolve'/'Editing Copilot.py',integration/'Editing Copilot.py')
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed',
                '--name','EditingCopilot','--paths',str(root/'src'),
                '--add-data',str(root/'resources')+';resources',
                '--hidden-import','win32com.client','--hidden-import','pythoncom',
                '--hidden-import','pywintypes','--collect-all','vosk','--collect-all','rapidocr_onnxruntime','--collect-all','pywinauto','--collect-all','sounddevice','--copy-metadata','pywin32',
                '--distpath',str(output),'--workpath',str(root/'build'),
                '--specpath',str(root/'build'),str(root/'launcher.py')],cwd=root,check=True)
print(json.dumps({'executable':str(output/'EditingCopilot.exe'),'bytes':(output/'EditingCopilot.exe').stat().st_size}))

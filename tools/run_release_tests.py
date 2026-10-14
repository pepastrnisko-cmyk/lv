"""Record executed tests without converting skipped integrations into passes."""
import json
import platform
from pathlib import Path
import sys
import time
import unittest
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
class Result(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.records=[]
    def addSuccess(self,test):
        super().addSuccess(test);self.records.append({'test':test.id(),'status':'pass'})
    def addFailure(self,test,err):
        super().addFailure(test,err);self.records.append({'test':test.id(),'status':'fail','detail':self._exc_info_to_string(err,test)})
    def addError(self,test,err):
        super().addError(test,err);self.records.append({'test':test.id(),'status':'error','detail':self._exc_info_to_string(err,test)})
    def addSkip(self,test,reason):
        super().addSkip(test,reason);self.records.append({'test':test.id(),'status':'skip','reason':reason})

suite=unittest.defaultTestLoader.discover(str(root/'tests'))
started=time.monotonic()
result=unittest.TextTestRunner(verbosity=1,resultclass=Result).run(suite)
report={'product':'Editing Copilot','version':'0.1.0','executed_utc':datetime.now(timezone.utc).isoformat(),
        'os':platform.platform(),'python':platform.python_version(),'tests_run':result.testsRun,
        'passed':sum(x['status']=='pass' for x in result.records),'failed':len(result.failures),
        'errors':len(result.errors),'skipped':len(result.skipped),'elapsed_seconds':round(time.monotonic()-started,3),
        'status':'pass' if result.wasSuccessful() else 'fail','tests':result.records,
        'scope':'Core candidate automated tests, Tk UI smoke, installed MLT rendering. Not the full v2 production qualification.',
        'remaining':['Resolve live API mutation unavailable under current configuration',
                     'real microphone recognition not validated','all v2 advanced AI features not implemented',
                     'no code-signing certificate','no enterprise Microsoft 365 tenant integration','no 8-hour soak certification']}
destination=Path(sys.argv[1]) if len(sys.argv)>1 else root/'release-test-results.json'
destination.parent.mkdir(parents=True,exist_ok=True)
destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
sys.exit(0 if result.wasSuccessful() else 1)

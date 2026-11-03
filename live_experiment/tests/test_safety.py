import json
import subprocess
import sys
import unittest

from live_experiment.safety import host_allowed


class BoundaryTests(unittest.TestCase):
    def test_exact_host_policy_rejects_suffix_spoofs_and_local_ips(self):
        sources={'query1.finance.yahoo.com'}
        self.assertTrue(host_allowed('api.openai.com',sources))
        self.assertTrue(host_allowed('QUERY1.FINANCE.YAHOO.COM.',sources))
        for host in ('evilapi.openai.com','api.openai.com.evil','localhost','127.0.0.1','query1.finance.yahoo.com.evil',''):
            self.assertFalse(host_allowed(host,sources))

    def test_guard_blocks_process_and_loopback_in_isolated_child(self):
        script='''
import json,socket,subprocess,sys,types
mock=types.ModuleType('live_experiment.source_http');mock.SOURCE_HOSTS={'query1.finance.yahoo.com'}
sys.modules['live_experiment.source_http']=mock
from live_experiment.safety import network_guard
network_guard()
result=[]
for action in (lambda:socket.getaddrinfo('unapproved.invalid',443),
               lambda:socket.socket().connect(('127.0.0.1',443)),
               lambda:subprocess.run([sys.executable,'-c','raise SystemExit(99)'])):
    try:action();result.append(False)
    except PermissionError:result.append(True)
print(json.dumps(result))
'''
        process=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout),[True,True,True])


if __name__=='__main__':unittest.main()

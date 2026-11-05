"""Operator-host tests; optional wheel acceptance uses clean external installation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from continuous_verification import digest
from continuous_verification.host import (
    CLIENT_OPERATIONS, HostError, client_session, collector_session, initialize,
    load_config, main, mcp_main,
)
from continuous_verification.service import ServiceError

ROOT = Path(__file__).resolve().parents[1]


class HostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="authored portable host ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "operator config.json"
        self.body = json.loads((ROOT / "examples/portable_host/new-host.json").read_text())
        self.packet = json.loads((ROOT / "continuous_verification/schemas/example.json").read_text())
        self.save()

    def save(self, value=None):
        self.config.write_text(json.dumps(self.body if value is None else value), encoding="utf-8")

    def seed_failure(self):
        initialize(self.config)
        events = copy.deepcopy(self.packet["events"])
        events[0]["payload"]["status"] = "ERROR"
        with collector_session(self.config) as collector:
            collector.execute("ingest_events", dict(run_id="authored-run", batch_id="authored-batch", events=events))
            collector.record_coverage("authored-run", "host", self.packet["checkpoint"]["streams"][0]["capabilities"])
            cp = collector.execute("checkpoint", dict(run_id="authored-run", checkpoint_id="checkpoint-1", revision=0,
                registry_revision=0, streams=[dict(stream_id="host", requested=3)]))
        request = copy.deepcopy(self.packet["request"])
        request["checkpoint"]["digest"] = digest(cp)
        return request

    def test_missing_config_and_uninitialized_state_fail_without_mcp_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(["--config", str(self.config) + ".missing", "get_run_state"]), 3)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], "CONFIG_ERROR")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(mcp_main(["--config", str(self.config)]), 3)
        self.assertEqual(out.getvalue(), "")
        self.assertFalse(load_config(self.config).state.exists())

    def test_empty_initialization_cannot_manufacture_assessment_or_coverage(self):
        self.assertEqual(initialize(self.config)["observations_seeded"], 0)
        with client_session(self.config) as client:
            state = client.call("get_run_state", {"run_id": "authored-run"})["result"]
            self.assertEqual(state["raw_ingested_events"], 0)
            self.assertFalse(state["atomic_semantic_ready"])
            self.assertEqual({c["state"] for c in state["coverage"]["host"]}, {"UNKNOWN"})
            self.assertEqual(client.call("verify", self.packet["request"])["error"]["code"], "NOT_FOUND")
            self.assertEqual(client.call("checkpoint", {"run_id": "authored-run"})["error"]["code"], "FORBIDDEN")
        before = load_config(self.config).database.read_bytes()
        with self.assertRaises(HostError):
            initialize(self.config)
        self.assertEqual(load_config(self.config).database.read_bytes(), before)

    def test_real_host_preserves_hold_and_separates_collector_and_client(self):
        request = self.seed_failure()
        with collector_session(self.config) as collector:
            with self.assertRaises(ServiceError):
                collector.execute("verify", request)
        with client_session(self.config) as client:
            response = client.call("verify", request)
            self.assertTrue(response["ok"])
            self.assertEqual(response["result"]["disposition"], "HOLD")
            self.assertIn("FAIL", [f["outcome"] for f in response["result"]["findings"]])
            for operation in ("ingest_events", "register_run", "checkpoint", "acknowledge_feedback"):
                self.assertEqual(client.call(operation, {"run_id": "authored-run"})["error"]["code"], "FORBIDDEN")
            with ThreadPoolExecutor(max_workers=3) as pool:
                reads = list(pool.map(lambda _: client.call("get_run_state", {"run_id": "authored-run"}), range(6)))
            self.assertTrue(all(read["ok"] for read in reads))
        request_file = self.root / "-request & literal.json"
        request_file.write_text(json.dumps(request), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--config", str(self.config), "verify", "--request", str(request_file)]), 0)
        self.assertEqual(json.loads(out.getvalue()), response)

    def test_existing_profile_reads_copy_without_bootstrap_or_original_mutation(self):
        request = self.seed_failure()
        with client_session(self.config) as client:
            expected = client.call("verify", request)
        original = load_config(self.config).database
        before = hashlib.sha256(original.read_bytes()).hexdigest()
        copied = self.root / "copied.sqlite"
        shutil.copyfile(original, copied)
        profile = self.root / "existing.json"
        body = dict(config_version="trustkernel-host-1", mode="existing", database=copied.name,
                    service_id="authored-service", client_id="copy-reader", run_ids=["authored-run"])
        profile.write_text(json.dumps(body))
        with client_session(profile) as client:
            self.assertEqual(client.call("verify", request), expected)
        with self.assertRaises(HostError): initialize(profile)
        with self.assertRaises(HostError):
            with collector_session(profile): pass
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), before)
        body["database"] = "absent.sqlite"
        profile.write_text(json.dumps(body))
        with self.assertRaises(HostError):
            with client_session(profile): pass
        self.assertFalse((self.root / "absent.sqlite").exists())

    def test_strict_config_no_paths_permissions_or_identity_injection(self):
        for mutate in (
            lambda c: c.update(permissions=["collect"]),
            lambda c: c.update(state_directory="../escape"),
            lambda c: c.update(client_id=c["collector_id"]),
            lambda c: c["runs"][0]["streams"][0].update(collector_id="model-selected"),
            lambda c: c["runs"][0]["policy"].update(unknown=True),
        ):
            body = copy.deepcopy(self.body)
            mutate(body)
            self.save(body)
            with self.assertRaises(HostError): load_config(self.config)
        self.config.write_text('{"config_version":"a","config_version":"b"}')
        with self.assertRaises(HostError): load_config(self.config)
        self.assertFalse((self.root / self.body["state_directory"]).exists())


# Standalone acceptance runs from the installed wheel, never the source checkout.
INSTALLED_CHECK = r'''
import asyncio,copy,hashlib,importlib.resources as resources,json,os,shutil,subprocess,sys
from pathlib import Path
import continuous_verification as package
from continuous_verification import digest
from continuous_verification.host import client_session,collector_session,load_config
from continuous_verification.service import Principal,ServiceBackend
from continuous_verification.tradingagents import LocalServiceWorker
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
root=Path(sys.argv[1]); repo=Path(sys.argv[2])
assert not Path(package.__file__).resolve().is_relative_to(repo)
assert 'PYTHONPATH' not in os.environ
pkt=json.loads(resources.files(package).joinpath('schemas/example.json').read_text())
assert resources.files(package).joinpath('prompts/tradingagents.md').read_text()
scripts=Path(sys.executable).parent
cli=scripts/('trustkernel.exe' if os.name=='nt' else 'trustkernel')
mcp=scripts/('trustkernel-mcp.exe' if os.name=='nt' else 'trustkernel-mcp')
def command(args,**kwargs):
    return subprocess.run([str(cli),*args],text=True,capture_output=True,timeout=20,**kwargs)
cfg=root/'operator config.json'
run=dict(run_id='authored-run',registration_id='registration-1',streams=[dict(stream_id='host',producer_id='authored-host',adapter_version='fixture-1',redaction_profile='authored-public')],policy=pkt['policy'])
other=copy.deepcopy(run);other['run_id']='other-run'
body=dict(config_version='trustkernel-host-1',mode='new',state_directory='new-state',service_id='authored-service',collector_id='collector',client_id='reader',runs=[run,other])
cfg.write_text(json.dumps(body))
r=command(['--config',str(cfg),'init']);assert r.returncode==0,r.stderr
assert json.loads(r.stdout)['result']['observations_seeded']==0
events=copy.deepcopy(pkt['events']);events[0]['payload']['status']='ERROR'
with collector_session(cfg) as collector:
    collector.execute('ingest_events',dict(run_id='authored-run',batch_id='authored',events=events))
    collector.record_coverage('authored-run','host',pkt['checkpoint']['streams'][0]['capabilities'])
    cp=collector.execute('checkpoint',dict(run_id='authored-run',checkpoint_id='checkpoint-1',revision=0,registry_revision=0,streams=[dict(stream_id='host',requested=3)]))
request=copy.deepcopy(pkt['request']);request['checkpoint']['digest']=digest(cp)
with client_session(cfg) as sdk:
    expected=sdk.call('verify',request)
assert expected['ok'] and expected['result']['disposition']=='HOLD'
assert 'FAIL' in [f['outcome'] for f in expected['result']['findings']]
request_file=root/'-request & literal.json';request_file.write_text(json.dumps(request))
r=command(['--config',str(cfg),'verify','--request',str(request_file)])
assert r.returncode==0 and json.loads(r.stdout)==expected,(r.stdout,r.stderr)
original=load_config(cfg).database;before=hashlib.sha256(original.read_bytes()).hexdigest()
copied=root/'copied-journal.sqlite';shutil.copyfile(original,copied)
existing=root/'existing.json';existing.write_text(json.dumps(dict(config_version='trustkernel-host-1',mode='existing',database=copied.name,service_id='authored-service',client_id='reader',run_ids=['authored-run','other-run'])))
r=command(['--config',str(existing),'verify','--request',str(request_file)])
assert r.returncode==0 and json.loads(r.stdout)==expected
async def session(cursor=None):
    params=StdioServerParameters(command=str(mcp),args=['--config',str(existing)],cwd=str(root))
    async with stdio_client(params) as (read,write):
        async with ClientSession(read,write) as s:
            await s.initialize()
            listed=await s.list_tools()
            assert {t.name for t in listed.tools}=={'verify','get_assessment','get_evidence','get_run_state','list_events'}
            result=await s.call_tool('verify',{'request':request})
            assert not result.isError and json.loads(result.content[0].text)==expected
            result=await s.call_tool('get_assessment',{'request':dict(run_id='authored-run',assessment_id=expected['result']['assessment_id'])})
            assert json.loads(result.content[0].text)==expected
            forbidden=await s.call_tool('get_evidence',{'request':dict(run_id='other-run',event_id='event-1')})
            assert json.loads(forbidden.content[0].text)['error']['code']=='FORBIDDEN'
            missing_tool=await s.call_tool('ingest_events',{'request':dict(run_id='authored-run')})
            assert missing_tool.isError
            bad=copy.deepcopy(request);bad['database']='not-a-server-file'
            rejected=await s.call_tool('verify',{'request':bad})
            assert json.loads(rejected.content[0].text)['error']['code']=='INVALID_REQUEST'
            page=await s.call_tool('list_events',{'request':dict(run_id='authored-run',after_cursor=cursor,limit=1 if cursor is None else 100)})
            return json.loads(page.content[0].text)['result']
first=asyncio.run(session());assert first['next_cursor']
# Only explicit trusted host code has collector authority; not the configured client.
worker=LocalServiceWorker(lambda:ServiceBackend(copied,principal=Principal('collector',frozenset({'collect'}),frozenset({'authored-run'})),service_id='authored-service'))
try:
    late=copy.deepcopy(events[0]);late.update(event_id='late-4',sequence=4)
    worker.execute('ingest_events',dict(run_id='authored-run',batch_id='late',events=[late]))
finally:worker.close()
second=asyncio.run(session(first['next_cursor']))
assert second['snapshot_id']==first['snapshot_id']
assert [e['event_id'] for e in second['events']]==['event-2','event-3']
assert second['next_cursor'] is None and not second['has_more']
assert hashlib.sha256(original.read_bytes()).hexdigest()==before
no_config=subprocess.run([str(mcp)],capture_output=True,text=True,timeout=15)
assert no_config.returncode!=0 and no_config.stdout==''
print(json.dumps({'status':'PASS','installed_module':str(package.__file__),'mcp_tools':5,'result':'HOLD','source_checkouts_used':False,'original_authored_store_unchanged':True}))
'''


@unittest.skipUnless(os.environ.get("TRUSTKERNEL_TEST_WHEEL") and os.environ.get("TRUSTKERNEL_TEST_WHEELHOUSE"),
                     "MISSING wheel/wheelhouse: clean-install genuine MCP acceptance unexecuted")
class InstalledWheelTests(unittest.TestCase):
    def test_clean_external_wheel_sdk_cli_mcp_persisted_hold_restart_and_denial(self):
        import venv
        wheel = Path(os.environ["TRUSTKERNEL_TEST_WHEEL"]).resolve()
        wheelhouse = Path(os.environ["TRUSTKERNEL_TEST_WHEELHOUSE"]).resolve()
        with tempfile.TemporaryDirectory(prefix="authored installed wheel ") as directory:
            root = Path(directory)
            self.assertFalse(root.resolve().is_relative_to(ROOT))
            environment = root / "clean-env"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
            env["PIP_NO_INDEX"] = "1"
            env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
            base = subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
                cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(base.returncode, 0, base.stderr)
            lean = subprocess.run([str(python), "-I", "-c",
                "import continuous_verification.host; import importlib.util; assert importlib.util.find_spec('mcp') is None"],
                cwd=root, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(lean.returncode, 0, lean.stderr)
            installed = subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--find-links",
                str(wheelhouse), str(wheel) + "[mcp]"], cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            script = root / "installed_check.py"
            script.write_text(INSTALLED_CHECK, encoding="utf-8")
            checked = subprocess.run([str(python), "-I", str(script), str(root), str(ROOT)],
                cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(json.loads(checked.stdout)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

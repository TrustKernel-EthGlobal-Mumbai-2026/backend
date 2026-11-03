import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path

from live_experiment.window import EventMonitor,validate_preflight


class WindowControlTests(unittest.TestCase):
    def report(self):
        return {'status':'PASS','core_ready':True,'model_calls':0,
            'ended_at':datetime.now(timezone.utc).isoformat(),'as_of':datetime.now().date().isoformat(),
            'providers':{k:{'status':'AVAILABLE','content':'native provider text'} for k in ('get_stock_data','get_verified_market_snapshot')},
            'events':[{'kind':'source.http.end','payload':{'status':200,'url':'https://query2.finance.yahoo.com/v8/finance/chart/ETH-USD'}}]}

    def test_preflight_blocks_stale_date_core_failure_and_spoofed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'probe.json'
            valid=self.report();path.write_text(json.dumps(valid),encoding='utf-8')
            self.assertEqual(validate_preflight(path)['status'],'PASS')
            for mutate in (
                lambda p:p.update(ended_at=(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()),
                lambda p:p.update(as_of='2026-01-01'),
                lambda p:p['providers']['get_stock_data'].update(status='SOURCE_UNAVAILABLE'),
                lambda p:p['events'][0]['payload'].update(url='https://evilfinance.yahoo.com/v8/finance/chart/ETH-USD'),
                lambda p:p.update(model_calls=1)):
                report=self.report();mutate(report);path.write_text(json.dumps(report),encoding='utf-8')
                with self.assertRaises(PermissionError):validate_preflight(path)

    def test_monitor_handles_incomplete_last_line_and_stops_on_core_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'arm').mkdir();path=root/'arm/trace.jsonl'
            event={'kind':'evidence.retrieved','payload':{'tool':'get_stock_data','source_status':'SOURCE_UNAVAILABLE'}}
            encoded=json.dumps(event).encode();path.write_bytes(encoded[:20])
            monitor=EventMonitor();monitor.poll(root)
            with path.open('ab') as handle:handle.write(encoded[20:]+b'\n')
            with self.assertRaisesRegex(RuntimeError,'Core native source'):monitor.poll(root)

    def test_optional_source_gaps_are_recorded_without_core_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'arm').mkdir();path=root/'arm/trace.jsonl'
            event={'kind':'evidence.retrieved','payload':{'tool':'get_news','source_status':'SOURCE_UNAVAILABLE'}}
            path.write_text(json.dumps(event)+'\n',encoding='utf-8')
            EventMonitor().poll(root)

    def test_budget_hard_stop_and_arm_error_stop_supervision(self):
        for kind in ('budget.hard_stop','run.error'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);(root/'arm').mkdir()
                (root/'arm/trace.jsonl').write_text(json.dumps({'kind':kind,'payload':{'error_type':'PermissionError'}})+'\n',encoding='utf-8')
                with self.assertRaises((PermissionError,RuntimeError)):EventMonitor().poll(root)


if __name__=='__main__':unittest.main()

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from procedural_loop.adapters import ReplaySession, EXPIRED_AS_OF, REFRESH_AS_OF
from procedural_loop.runner import run_one, signatures
from procedural_loop.verifier import assess, validate_clearance


class IntegrationTests(unittest.TestCase):
    def test_complete_loop_both_shapes_and_equivalent_obligations(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root=Path(temporary)
            for shape in ('single','multi'):
                summary=run_one(shape,root/shape,'integration:'+shape)
                self.assertEqual([p['cleared'] for p in summary['phases']],[True,False,True])
                self.assertTrue(summary['old_clearance_reuse_rejected'])
                self.assertTrue(summary['distorted_extract_rejected'])
                events=[json.loads(x) for x in (root/shape/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
                kinds=[e['kind'] for e in events]
                ordered=['host.proposal.held','adapter.finding.delivered','adapter.host.acknowledged',
                         'host.refresh.requested','adapter.source.refresh_requested']
                indices=[kinds.index(k) for k in ordered]
                self.assertEqual(indices,sorted(indices))
                for phase in ('initial','expired','refreshed'):
                    packet=json.loads((root/shape/f'{phase}-packet.json').read_text(encoding='utf-8'))
                    for evidence in packet['evidence']:
                        parsed=urlparse(evidence['pointer']['uri'])
                        self.assertEqual(parsed.scheme,'file')
                        source=json.loads(Path(url2pathname(parsed.path)).read_text(encoding='utf-8'))
                        for part in evidence['pointer']['json_pointer'].strip('/').split('/'):
                            key=part.replace('~1','/').replace('~0','~')
                            source=source[int(key)] if isinstance(source,list) else source[key]
                        self.assertEqual(source,evidence['content'])
            self.assertEqual(signatures(root/'single'),signatures(root/'multi'))

    def test_unknown_coverage_and_wrong_version_cannot_clear(self):
        packet=ReplaySession('single').initial_packet()
        unknown=copy.deepcopy(packet)
        unknown['capabilities'][0]['state']='UNKNOWN'
        self.assertIsNone(assess(unknown)['clearance'])
        wrong=copy.deepcopy(packet)
        wrong['proposal']['extracts'][0]['source_version']='unobserved'
        self.assertIsNone(assess(wrong)['clearance'])

    def test_refresh_changes_context_without_rewriting_historical_clearance(self):
        session=ReplaySession('single')
        initial=session.initial_packet();historical=assess(initial)
        expired=session.advance_to(EXPIRED_AS_OF);failure=assess(expired)
        self.assertFalse(validate_clearance(historical['clearance'],expired))
        session.deliver_finding(failure);session.request_refresh(REFRESH_AS_OF)
        revised=session.revised_packet()
        self.assertIsNotNone(assess(revised)['clearance'])
        self.assertFalse(validate_clearance(historical['clearance'],revised))
        self.assertTrue(validate_clearance(historical['clearance'],initial))


if __name__=='__main__':
    unittest.main()

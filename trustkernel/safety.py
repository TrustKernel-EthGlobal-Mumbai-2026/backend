"""Execution boundaries and pessimistic request reservations. No retry spending."""
import socket
import sqlite3
import sys
import time
import math
import uuid
from contextlib import closing
from pathlib import Path
from .billing import upper_charge, message_usage


def network_guard(paid=False):
    # Installed after imports; persists for the lifetime of this child process.
    allowed = set()
    if paid:
        allowed = {entry[4][0] for entry in socket.getaddrinfo('api.openai.com', 443, type=socket.SOCK_STREAM)}

    def audit(event, args):
        if event == 'socket.getaddrinfo' and (not paid or args[0] != 'api.openai.com'):
            raise PermissionError('TrustKernel blocks non-OpenAI network access')
        if event == 'socket.connect':
            address = args[1]
            if not paid or not isinstance(address, tuple) or address[0] not in allowed or address[1] != 443:
                raise PermissionError('TrustKernel blocks this socket destination')
        if event in ('subprocess.Popen', 'os.system'):
            raise PermissionError('TrustKernel research child cannot launch subprocesses')
    sys.addaudithook(audit)


class Budget:
    def __init__(self, path, limit, model, deadline, stop_file, trace, max_calls=24, initial_limit=None):
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError('Budget must be finite and positive')
        if initial_limit is not None and (not math.isfinite(initial_limit) or not 0 < initial_limit <= limit):
            raise ValueError('Initial allowance must be positive and at most the hard limit')
        self.path, self.limit, self.model = path, limit, model
        self.initial_limit = initial_limit
        self.deadline, self.stop_file, self.trace = deadline, Path(stop_file), trace
        self.calls, self.max_calls = 0, max_calls
        self.pending = {}
        # Conservative maximum per request: 60k input tokens, 2048 output tokens.
        # Standard short-context prices verified 2026-10-29. No discount assumed.
        self.reserve = upper_charge(model, dict(input_tokens=60000, output_tokens=2048))
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), reserved REAL)')
            db.execute('INSERT OR IGNORE INTO budget VALUES (1,0)')
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, reserved REAL, charge REAL, status TEXT, response_id TEXT)')
            if initial_limit is not None:
                db.execute('CREATE TABLE IF NOT EXISTS budget_policy (id INTEGER PRIMARY KEY CHECK(id=1), initial_limit REAL, active_limit REAL, hard_limit REAL)')
                db.execute('INSERT OR IGNORE INTO budget_policy VALUES (1,?,?,?)', (initial_limit, initial_limit, limit))
                saved_initial, saved_hard = db.execute('SELECT initial_limit,hard_limit FROM budget_policy WHERE id=1').fetchone()
                if (saved_initial, saved_hard) != (initial_limit, limit):
                    raise PermissionError('Existing cumulative budget policy differs; automatic reset or increase prohibited')

    def before(self, messages, metadata):
        import json
        from .trace import plain
        if time.time() >= self.deadline or self.stop_file.exists():
            raise PermissionError('Deadline or STOP file reached')
        self.calls += 1
        if self.calls > self.max_calls:
            raise PermissionError('Per-arm request bound reached')
        # Serialized UTF-8 byte count overestimates text token counts. Tool/schema
        # payload included; reserve additional margin for SDK framing.
        size = len(json.dumps(plain([messages, metadata.get('invocation_params')]), ensure_ascii=False).encode())
        if size > 50000:
            raise PermissionError('Input exceeds conservative 50k-byte request envelope')
        request_id = str(uuid.uuid4())
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            reserved = db.execute('SELECT reserved FROM budget WHERE id=1').fetchone()[0]
            if reserved + self.reserve > self.limit:
                self.trace.emit('budget.hard_stop', dict(total_reserved_usd=reserved, denied_request_reserve_usd=self.reserve, hard_limit_usd=self.limit))
                raise PermissionError('Approved conservative budget exhausted')
            extended = False
            if self.initial_limit is not None:
                active = db.execute('SELECT active_limit FROM budget_policy WHERE id=1').fetchone()[0]
                if reserved + self.reserve > active:
                    db.execute('UPDATE budget_policy SET active_limit=? WHERE id=1', (self.limit,))
                    extended = True
            db.execute('UPDATE budget SET reserved=? WHERE id=1', (reserved + self.reserve,))
            db.execute('INSERT INTO requests VALUES (?,?,NULL,?,NULL)', (request_id, self.reserve, 'in_flight_or_unknown'))
        self.pending[str(metadata.get('run_id'))] = request_id
        if extended:
            self.trace.emit('budget.extended', dict(previous_limit_usd=self.initial_limit, active_limit_usd=self.limit,
                                                    reason='User preauthorized one extension; next reservation would cross initial allowance'))
            print(f'BUDGET: initial ${self.initial_limit:.2f} allowance extended once to ${self.limit:.2f}; hard stop remains enforced.', flush=True)
        self.trace.emit('budget.reserved', dict(request=self.calls, reserved_usd=self.reserve,
                                              total_reserved_usd=reserved + self.reserve,
                                              limit_usd=self.limit, input_bytes=size, request_id=request_id))

    def settle(self, response, metadata):
        from .trace import plain
        usage = message_usage(plain(response))
        request_id = self.pending.get(str(metadata.get('run_id')))
        if len(usage) != 1 or not request_id:
            self.trace.emit('budget.usage_unknown', dict(request_id=request_id, full_reservation_retained=True))
            return
        response_id, tokens = next(iter(usage.items()))
        charge = upper_charge(self.model, tokens)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            held, status = db.execute('SELECT reserved,status FROM requests WHERE id=?', (request_id,)).fetchone()
            if status == 'settled':
                return
            if charge > held:
                raise PermissionError('Provider usage exceeded reservation; further requests prohibited')
            balance = db.execute('SELECT reserved FROM budget WHERE id=1').fetchone()[0]
            balance = max(0, balance-held+charge)
            db.execute('UPDATE budget SET reserved=? WHERE id=1', (balance,))
            db.execute('UPDATE requests SET charge=?,status=?,response_id=? WHERE id=?',
                       (charge, 'settled', response_id, request_id))
        self.trace.emit('budget.settled', dict(request_id=request_id, response_id=response_id,
                                             usage=tokens, charged_upper_usd=charge,
                                             released_reservation_usd=held-charge,
                                             total_committed_upper_usd=balance))

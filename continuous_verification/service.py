"""Offline storage facade. Public contract/verifier binding is pending lane A.

This facade deliberately has no verify/checkpoint-success implementation.
"""
from .capture import TraceTailer
from .journal import Journal
from .projection import Projection


class CaptureService:
    def __init__(self, journal_path):
        self.journal = Journal(journal_path)
        self.journal.audit()
        self.projection = Projection()

    def ingest_trace(self, source_id, path):
        return TraceTailer(self.journal, source_id, path).poll()

    def project(self, through=None):
        self.projection.advance(self.journal, through)

    def storage_snapshot(self, required_position, streams=None):
        return self.projection.snapshot(self.journal, required_position=required_position, streams=streams)

    def close(self):
        self.journal.close()

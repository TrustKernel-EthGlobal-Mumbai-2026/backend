"""Read-only observable trace adapter. No execution or wallet capability."""
import os

# Never inherit hosted tracing/export settings from the user's shell.
os.environ['LANGCHAIN_TRACING_V2'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
os.environ['LANGCHAIN_TRACING'] = 'false'
os.environ['TRADINGAGENTS_NO_UPDATE_CHECK'] = '1'
__version__ = "0.1.0"

import runpy
from pathlib import Path
from unittest.mock import Mock

import uvicorn


def test_production_entrypoint_honors_host_port_without_starting_a_server(monkeypatch):
    run = Mock()
    monkeypatch.setattr(uvicorn, 'run', run)
    monkeypatch.setenv('PORT', '9123')
    runpy.run_path(str(Path(__file__).parents[1] / 'start_server.py'), run_name='__main__')
    args, options = run.call_args
    assert args == ('main:app',)
    assert options['host'] == '0.0.0.0' and options['port'] == 9123
    assert options['workers'] == 1
    assert options['access_log'] is False and options['log_level'] == 'warning'
    assert options['ws_max_size'] == 768 * 1024

"""
Tests for KiCad configuration load

For debug information use:
pytest-3 --log-cli-level debug
"""

import os
import sys
import pytest
import coverage
import logging
import sysconfig
# Look for the 'utils' module from where the script is running
prev_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if prev_dir not in sys.path:
    sys.path.insert(0, prev_dir)
# Utils import
from utils import context
# One more level for the project
prev_dir = os.path.dirname(prev_dir)
if prev_dir not in sys.path:
    sys.path.insert(0, prev_dir)
from kiplot.misc import EXIT_BAD_CONFIG
from kiplot.kicad.config import KiConf, KiConfError
from kiplot.gs import GS


cov = coverage.Coverage()
_real_posix_prefix = None


def test_kicad_conf_bad_sym_lib_table():
    """ Check various problems in the sym-lib-table file """
    sch = 'sym-lib-table_errors/kibom-test'
    test = 'test_kicad_conf_bad_sym_lib_table'
    ctx = context.TestContextSCH(test, sch, 'int_bom_simple_csv', None)
    ctx.run(EXIT_BAD_CONFIG, extra_debug=True)
    ctx.search_err('Malformed lib entry')
    ctx.search_err(r'Unable to expand .?BOGUS.? in')
    ctx.search_err(r'unnamed LibAlias')
    ctx.clean_up()


def test_kicad_conf_no_instance():
    """ Check we can't create a KiConf instance """
    cov.load()
    cov.start()
    with pytest.raises(AssertionError) as pytest_wrapped_e:
        o = KiConf()  # noqa: F841
    cov.stop()
    cov.save()
    assert pytest_wrapped_e.type == AssertionError
    assert str(pytest_wrapped_e.value) == 'KiConf is fully static, no instances allowed'


def kiconf_de_init():
    KiConf.loaded = False
    KiConf.config_dir = None
    KiConf.dirname = None
    KiConf.sym_lib_dir = None
    KiConf.kicad_env = {}
    KiConf.lib_aliases = {}


def check_load_conf(caplog, dir='kicad', fail=False, catch_conf_error=False):
    caplog.set_level(logging.DEBUG)
    kiconf_de_init()
    cov.load()
    cov.start()
    if catch_conf_error:
        with pytest.raises(KiConfError) as err:
            KiConf.init(os.path.join(context.BOARDS_DIR, 'v5_errors/kibom-test.sch'))
    else:
        KiConf.init(os.path.join(context.BOARDS_DIR, 'v5_errors/kibom-test.sch'))
        err = None
    cov.stop()
    cov.save()
    ref = 'Reading KiCad config from `tests/data/'+dir+'/kicad_common`'
    if fail:
        ref = 'Unable to find KiCad configuration file'
    assert ref in caplog.text, caplog.text
    return err


def test_kicad_conf_user(caplog, monkeypatch):
    """ Check we can load the KiCad configuration from $KICAD_CONFIG_HOME """
    GS.debug_level = 2
    with monkeypatch.context() as m:
        m.setenv("KICAD_CONFIG_HOME", 'tests/data/kicad_ok')
        check_load_conf(caplog, dir='kicad_ok')
    assert 'KICAD_TEMPLATE_DIR="/usr/share/kicad/template"' in caplog.text, caplog.text


def test_kicad_conf_xdg(caplog, monkeypatch):
    """ Check we can load the KiCad configuration from $XDG_CONFIG_HOME/kicad """
    with monkeypatch.context() as m:
        m.setenv("XDG_CONFIG_HOME", 'tests/data')
        check_load_conf(caplog)
    assert 'KiCad config without EnvironmentVariables section' in caplog.text, caplog.text


def test_kicad_conf_miss_home(caplog, monkeypatch):
    """ Check no HOME and fail to load kicad_common.
        Also check we correctly guess the libs dir. """
    with monkeypatch.context() as m:
        m.setenv("HOME", '')
        check_load_conf(caplog, fail=True)
    assert '`HOME` not defined' in caplog.text, caplog.text
    assert 'Detected KICAD_SYMBOL_DIR="/usr/share/kicad/library"' in caplog.text, caplog.text


def test_kicad_conf_lib_env(caplog, monkeypatch):
    """ Check we can use KICAD_SYMBOL_DIR as fallback """
    with monkeypatch.context() as m:
        m.setenv("HOME", '')
        m.setenv("KICAD_SYMBOL_DIR", 'tests')
        check_load_conf(caplog, fail=True)
    assert '`HOME` not defined' in caplog.text, caplog.text
    assert 'Detected KICAD_SYMBOL_DIR="tests"' in caplog.text, caplog.text


def test_kicad_conf_sym_err_1(caplog, monkeypatch):
    """ Test broken sym-lib-table, no signature """
    GS.debug_level = 2
    with monkeypatch.context() as m:
        m.setenv("KICAD_CONFIG_HOME", 'tests/data/kicad_err_1')
        err = check_load_conf(caplog, dir='kicad_err_1', catch_conf_error=True)
    assert err.type == KiConfError
    assert err.value.msg == 'Symbol libs table missing signature'
    assert err.value.line == 1


def test_kicad_conf_sym_err_2(caplog, monkeypatch):
    """ Test broken sym-lib-table, wrong entry """
    GS.debug_level = 2
    with monkeypatch.context() as m:
        m.setenv("KICAD_CONFIG_HOME", 'tests/data/kicad_err_2')
        err = check_load_conf(caplog, dir='kicad_err_2', catch_conf_error=True)
    assert err.type == KiConfError
    assert err.value.msg == 'Unknown symbol table entry'
    assert err.value.line == 2


def mocked_get_path_1(name, scheme):
    """ Pretend the system libs are the user ones.
        Disable the system libs. """
    if name == 'data':
        if scheme == 'posix_user':
            return _real_posix_prefix
        elif scheme == 'posix_prefix':
            return ''
    return sysconfig.get_path(name, scheme)


def test_kicad_conf_local_conf(caplog, monkeypatch):
    """ Test if we can use the 'posix_user' """
    global _real_posix_prefix
    _real_posix_prefix = sysconfig.get_path('data', 'posix_prefix')
    with monkeypatch.context() as m:
        m.setattr("sysconfig.get_path", mocked_get_path_1)
        cov.load()
        cov.start()
        assert KiConf.guess_symbol_dir() == '/usr/share/kicad/library'
        cov.stop()
        cov.save()


def test_kicad_conf_no_conf(caplog, monkeypatch):
    """ Test a complete fail to find libs """
    with monkeypatch.context() as m:
        m.setattr("sysconfig.get_path", lambda a, b: '')
        m.setenv('HOME', '')
        check_load_conf(caplog, fail=True)
    assert 'Unable to find KiCad libraries' in caplog.text, caplog.text
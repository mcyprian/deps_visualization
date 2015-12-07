import pytest
from flexmock import flexmock
import sys
import os
import shutil


from sclbuilder.utils import subprocess_popen_call
from sclbuilder.pkg_source_plugins.dnf import DnfArchive

tests_dir = os.path.split(os.path.abspath(__file__))[0]

class TestPkgSource(object):
    
    @pytest.mark.parametrize(('input_path', 'expected'), [
        (tests_dir + '/test', tests_dir + '/test/'),
        (tests_dir + '/test/', tests_dir + '/test/')
    ])
    def test_pkg_dir(self, input_path, expected):
        flexmock(DnfArchive).should_receive('download').once()
        flexmock(DnfArchive).should_receive('pack').once()
        flexmock(DnfArchive).should_receive('unpack').once()
        flexmock(DnfArchive, rpms_from_spec=['pkg1', 'pkg2'])
        pkg_source = DnfArchive('pkg', input_path)
        assert pkg_source.pkg_dir == expected
        shutil.rmtree(tests_dir + '/test/')


#    @pytest.mark.parametrize(('srpms', 'expected'), [
#        ('''
#         python-flask-0.10.1-7.fc23.noarch
#         python-flask-doc-0.10.1-7.fc23.noarch
#         python3-flask-0.10.1-7.fc23.noarch
#         python3-flask-doc-0.10.1-7.fc23.noarch
#         ''', {'python-flask', 'python3-flask'})
#    ])
#    def test_rpms_from_spec(self, srpms, expected):
#        flexmock(DnfArchive).should_receive('download').once()
#        flexmock(DnfArchive).should_receive('pack').once()
#        flexmock(DnfArchive).should_receive('unpack').once()
#        flexmock(sys.modules[__name__]).should_receive('subprocess_popen_call')\
#        .and_return({'stdout' : srpms})
#        pkg_source = DnfArchive('pkg', 'dir')
#        assert pkg_source.rpms_from_spec == expected
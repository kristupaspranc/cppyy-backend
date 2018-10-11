import os, sys, glob, subprocess
from setuptools import setup, find_packages, Extension
from distutils import log
from distutils.command.build_ext import build_ext as _build_ext
from distutils.command.clean import clean as _clean
from distutils.dir_util import remove_tree
from setuptools.command.install import install as _install
try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
    has_wheel = True
except ImportError:
    has_wheel = False
from distutils.errors import DistutilsSetupError
from codecs import open


here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

_is_manylinux = None
def is_manylinux():
    global _is_manylinux
    if _is_manylinux is None:
        _is_manylinux = False
        try:
            for line in open('/etc/redhat-release').readlines():
                if 'CentOS release 5.11' in line:
                    _is_manylinux = True
                    break
        except (OSError, IOError):
            pass
    return _is_manylinux

try:
    root_install = os.environ["ROOTSYS"]
    requirements = []
    add_pkg = ['cppyy_backend']
except KeyError:
    root_install = None
    requirements = ['cppyy-cling>6.14.2.1']
    add_pkg = []

def _get_config_exec():
    if root_install:
        return ['root-config']
    return ['python', '-m', 'cppyy_backend._cling_config']

def get_include_path():
    config_exec_args = _get_config_exec()
    config_exec_args.append('--incdir')
    cli_arg = subprocess.check_output(config_exec_args)
    return cli_arg.decode("utf-8").strip()

def get_cflags():
    config_exec_args = _get_config_exec()
    config_exec_args.append('--auxcflags')
    cli_arg = subprocess.check_output(config_exec_args)
    return cli_arg.decode("utf-8").strip()

class my_build_cpplib(_build_ext):
    def build_extension(self, ext):
        include_dirs = ext.include_dirs + [get_include_path()]
        log.info('checking for %s', self.build_temp)
        if not os.path.exists(self.build_temp):
            log.info('creating %s', self.build_temp)
            os.makedirs(self.build_temp)
        objects = self.compiler.compile(
            ext.sources,
            output_dir=self.build_temp,
            include_dirs=include_dirs,
            debug=self.debug,
            extra_postargs=['-O2']+get_cflags().split())

        ext_path = self.get_ext_fullpath(ext.name)
        output_dir = os.path.dirname(ext_path)
        full_libname = 'libcppyy_backend.so' # forced, b/c hard-wired in pypy-c/cppyy
        extra_preargs = list()
        if 'linux' in sys.platform:
            extra_preargs += ['-Wl,-Bsymbolic-functions']

        log.info("now building %s", full_libname)
        self.compiler.link_shared_object(
            objects, full_libname,
            build_temp=self.build_temp,
            output_dir=output_dir,
            debug=self.debug,
            target_lang='c++',
            extra_preargs=extra_preargs)

class my_clean(_clean):
    def run(self):
        # Custom clean. Clean everything except that which the base clean
        # (see below) or create_src_directory.py is responsible for.
        topdir = os.getcwd()
        if self.all:
            # remove build directories
            for directory in (os.path.join(topdir, "dist"),
                              os.path.join(topdir, "python", "cppyy_backend.egg-info")):
                if os.path.exists(directory):
                    remove_tree(directory, dry_run=self.dry_run)
                else:
                    log.warn("'%s' does not exist -- can't clean it",
                             directory)
        # Base clean.
        _clean.run(self)

class my_install(_install):
    def _get_install_path(self):
        # depending on goal, copy over pre-installed tree
        if hasattr(self, 'bdist_dir') and self.bdist_dir:
            install_path = self.bdist_dir
        else:
            install_path = self.install_lib
        return install_path

    def run(self):
        # base install
        _install.run(self)

        # custom install of backend
        log.info('Now installing cppyy_backend')
        builddir = self.build_lib
        if not os.path.exists(builddir):
            raise DistutilsSetupError('Failed to find build dir!')

        install_path = self._get_install_path()
        log.info('Copying installation to: %s ...', install_path)
        self.copy_tree(builddir, install_path)

        log.info('Install finished')

    def get_outputs(self):
        outputs = _install.get_outputs(self)
        #outputs.append(os.path.join(self._get_install_path(), 'cppyy_backend'))
        return outputs

cmdclass = {
        'build_ext': my_build_cpplib,
        'clean': my_clean,
        'install': my_install }
if has_wheel:
    class my_bdist_wheel(_bdist_wheel):
        def run(self, *args):
         # wheels do not respect dependencies; make this a no-op, unless it is
         # explicit building for manylinux
            if is_manylinux():
                return _bdist_wheel.run(self, *args)

        def finalize_options(self):
         # this is a universal, but platform-specific package; a combination
         # that wheel does not recognize, thus simply fool it
            from distutils.util import get_platform
            self.plat_name = get_platform()
            self.universal = True
            _bdist_wheel.finalize_options(self)
            self.root_is_pure = True
    cmdclass['bdist_wheel'] = my_bdist_wheel


setup(
    name='cppyy-backend',
    description='C/C++ wrapper for Cling',
    long_description=long_description,
    url='http://pypy.org',

    # Author details
    author='PyPy Developers',
    author_email='pypy-dev@python.org',

    version='1.4.3',

    license='LBNL BSD',

    classifiers=[
        'Development Status :: 5 - Production/Stable',

        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',

        'Topic :: Software Development',
        'Topic :: Software Development :: Interpreters',

        'License :: OSI Approved :: BSD License',

        'Operating System :: POSIX',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',

        'Programming Language :: C',
        'Programming Language :: C++',

        'Natural Language :: English'
    ],

    keywords='C++ bindings data science',

    setup_requires=['wheel']+requirements,
    install_requires=requirements,

    package_dir={'': 'python'},
    packages=find_packages('python', include=add_pkg),

    ext_modules=[Extension('cppyy_backend/lib/libcppyy_backend',
        sources=glob.glob('src/clingwrapper.cxx'))],
    zip_safe=False,

    cmdclass = cmdclass
)

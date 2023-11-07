import codecs
import os.path
import setuptools


def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with codecs.open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()


def get_version(rel_path):
    for line in read(rel_path).splitlines():
        if line.startswith('__version__'):
            delim = '"' if '"' in line else "'"
            return line.split(delim)[1]
    else:
        raise RuntimeError("Unable to find version string.")


INSTALL_REQUIRES = [
    'ebmlite>=3.3.0',
    'idelib>=3.2.9',
    'numpy>=1.19.4',
    'psutil>=5.5.0; sys_platform == "linux" or sys_platform=="darwin"',
    'pyserial>=3.5',
    'pywin32>=228; sys_platform == "win32"'
]

TEST_REQUIRES = [
    'pytest>=7.2',
]

DOCS_REQUIRES = [
    'Sphinx==4.5.0',
    'sphinxcontrib-applehelp==1.0.2',
    'sphinxcontrib-devhelp==1.0.2',
    'sphinxcontrib-htmlhelp==2.0.0',
    'sphinxcontrib-jsmath==1.0.1',
    'sphinxcontrib-qthelp==1.0.3',
    'sphinxcontrib-serializinghtml==1.1.5',
    'pydata-sphinx-theme==0.7.1',
    'sphinx-autodoc-typehints==1.18.1',
]


setuptools.setup(
        name='endaq-device',
        version=get_version('endaq/device/__init__.py'),
        author='Mide Technology',
        author_email='help@mide.com',
        description='Python API for enDAQ data recorders',
        long_description=read('README.md'),
        long_description_content_type='text/markdown',
        url='https://github.com/MideTechnology/endaq-device',
        license='MIT',
        classifiers=['Development Status :: 5 - Production/Stable',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Programming Language :: Python :: 3.7',
                     'Programming Language :: Python :: 3.8',
                     'Programming Language :: Python :: 3.9',
                     'Programming Language :: Python :: 3.10',
                     'Programming Language :: Python :: 3.11',
                     'Programming Language :: Python :: 3.12',
                     ],
        keywords='endaq configure recorder hardware',
        project_urls={
            "Bug Tracker": "https://github.com/MideTechnology/endaq-device/issues",
            "Documentation": "https://mide-technology-endaq-device.readthedocs-hosted.com/en/latest/",
            "Source Code": "https://github.com/MideTechnology/endaq-device",
            },
        packages=[
            'endaq.device',
            'endaq.device.ui_defaults',
            'endaq.device.schemata',
            ],
        package_dir={
            'endaq.device': './endaq/device',
            },
        package_data={
            '': ['schemata/*.xml'],
        },
        test_suite='tests',
        install_requires=[
            'idelib>=3.2',
            'numpy>=1.19.4',
            'ebmlite>=3.1.0',
            'psutil>=5.5.0; sys_platform == "linux" or sys_platform=="darwin"',
            'pyserial>=3.5',
            'pywin32>=228; sys_platform == "win32"'
            ],
        extras_require={
            'test': INSTALL_REQUIRES + TEST_REQUIRES,
            'docs': INSTALL_REQUIRES + DOCS_REQUIRES,
            },
        # tests_require=[
        #     'pytest',
        #     'mock'
        #     ],
)

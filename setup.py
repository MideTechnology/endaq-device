import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()


INSTALL_REQUIRES = [
    'idelib>=3.2',
    'numpy>=1.19.4',
    'ebmlite>=3.1.0',
    'psutil>=5.5.0; sys_platform == "linux" or sys_platform=="darwin"',
    'pyserial>=3.5',
    'pywin32>=228; sys_platform == "win32"'
]

TEST_REQUIRES = [
    'pytest>=7.2',
]

with open('docs/requirements.txt', 'r') as fh:
    DOCS_REQUIRES = fh.readlines()


setuptools.setup(
        name='endaq-device',
        version='1.0.0b1',
        author='Mide Technology',
        author_email='help@mide.com',
        description='Python API for enDAQ data recorders',
        long_description=long_description,
        long_description_content_type='text/markdown',
        url='https://github.com/MideTechnology/endaq-device',
        license='MIT',
        classifiers=['Development Status :: 4 - Beta',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Programming Language :: Python :: 3.6',
                     'Programming Language :: Python :: 3.7',
                     'Programming Language :: Python :: 3.8',
                     'Programming Language :: Python :: 3.9',
                     'Programming Language :: Python :: 3.10',
                     ],
        keywords='endaq configure recorder hardware',
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

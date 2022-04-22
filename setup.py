import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
        name='endaq-device',
        version='1.0.0a1',
        author='Mide Technology',
        author_email='help@mide.com',
        description='Python API for enDAQ data recorders',
        long_description=long_description,
        long_description_content_type='text/markdown',
        url='https://github.com/MideTechnology/endaq-device',
        license='MIT',
        classifiers=['Development Status :: 3 - Alpha',
                     'License :: OSI Approved :: MIT License',
                     'Natural Language :: English',
                     'Programming Language :: Python :: 3.6',
                     'Programming Language :: Python :: 3.7',
                     'Programming Language :: Python :: 3.8',
                     'Programming Language :: Python :: 3.9',
                     ],
        keywords='endaq configure recorder hardware',
        packages=['endaq.device'],
        package_dirs={'endaq.device': './endaq/device'},
        package_data={
            '': ['schemata/*.xml', 'defaults/*.ui'],
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
        # tests_require=[
        #     'pytest',
        #     'mock'
        #     ],
)

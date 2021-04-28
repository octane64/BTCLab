from setuptools import setup, find_packages


setup(
    name='btclab',
    version='0.1',
    description='Script to operate with cryptos',
    license='GPL',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[i.strip() for i in open('requirements.txt').readlines()],
    entry_points='''
        [console_scripts]
        btclab=btclab.cli:main
    '''
)
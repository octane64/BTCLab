from setuptools import setup, find_packages


setup(
    name='buydips',
    version='0.1',
    description='Script to buy dips in the crypto markets',
    license='GPL',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[i.strip() for i in open('requirements.txt').readlines()],
    entry_points='''
        [console_scripts]
        btclab=btclab.buydips:main
    '''
)
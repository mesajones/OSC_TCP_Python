from setuptools import setup, find_packages

setup(
    name="pythonosctcp",
    version="2.0",
    packages=find_packages(),
    install_requires=[],
    package_data={
        '': ['*.txt', '*.md'],
    },
    author="Carey Chomsoonthorn",
    author_email="carey.chomsoonthorn@gmail.com",
    description="Python OSC TCP contains a simple TCP client that can use OSC.",
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.12',
        'Topic :: Software Development :: Libraries',
    ],
)
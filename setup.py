from setuptools import setup, find_packages

# Version managed by bumpversion, do not change it directly.
__version__ = '0.1.0'


setup(name='wasp-eureka',
      description='Async Eureka client',
      version=__version__,
      author='Matt Rasband',
      author_email='matt.rasband@gmail.com',
      license='Apache-2.0',
      url='https://github.com/wickedasp/eureka',
      download_url=('https://github.com/wickedasp/eureka'
                    '/archive/v' + __version__ + '.tar.gz'),
      keywords=[
          'microservice',
          'netflixoss',
          'asyncio',
          'springcloud',
      ],
      packages=find_packages(exclude=('examples',)),
      classifiers=[
          'Programming Language :: Python :: 3.5',
          'License :: OSI Approved :: Apache Software License',
          'Intended Audience :: Developers',
          'Development Status :: 4 - Beta',
          'Topic :: Software Development',
      ],
      setup_requires=[
          'pytest-runner',
          'flake8',
      ],
      install_requires=[
          'aiohttp',
      ],
      extras_require={},
      tests_require=[
          'pytest-aiohttp',
          'pytest'
      ],
      entry_points={},
      zip_safe=False)

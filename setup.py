from setuptools import setup

__version__ = '0.0.2'


setup(name='wasp-eureka',
      description=('Async Eureka client'),
      version=__version__,
      author='Matt Rasband',
      author_email='matt.rasband@gmail.com',
      license='Apache-2.0',
      url='https://github.com/wickedasp/eureka',
      download_url=('https://github.com/wickedasp/eureka'
                    '/archive/v' + __version__ + '.tar.bz2'),
      keywords=[
          'microservice',
          'netflixoss',
          'asyncio',
          'springcloud',
      ],
      py_modules=['wasp_eureka'],
      classifiers=[
          'Programming Language :: Python :: 3.5',
          'License :: OSI Approved :: Apache Software License',
          'Intended Audience :: Developers',
          'Development Status :: 2 - Pre-Alpha',
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

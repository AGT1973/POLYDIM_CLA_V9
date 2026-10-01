import os
import sys
from setuptools import setup, Extension
import pybind11

ext_modules = [
    Extension(
        'polydim_pybind_v911',
        ['ENTREGA_2026_09_30_V911/polydim_pybind_v911.cpp'],
        include_dirs=[
            pybind11.get_include(),
            pybind11.get_include(user=True)
        ],
        language='c++',
        extra_compile_args=['-O3', '-std=c++20', '-fopenmp', '-mavx', '-msse4.2'],
        extra_link_args=['-fopenmp'],
    ),
]

setup(
    name='polydim_pybind_v911',
    version='0.911',
    author='Polydim Project',
    description='POLYDIM V911 Native Extension',
    ext_modules=ext_modules,
)

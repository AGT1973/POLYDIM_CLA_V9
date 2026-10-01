import os
import sys
from setuptools import setup, Extension
import pybind11

ext_modules = [
    Extension(
        'polydim_pybind_v912',
        ['ENTREGA_2026_10_01_V912/polydim_pybind_v912.cpp'],
        include_dirs=[pybind11.get_include(), pybind11.get_include(user=True)],
        language='c++',
        extra_compile_args=['-O3', '-std=c++20', '-fopenmp', '-mavx', '-msse4.2'],
        extra_link_args=['-fopenmp'],
    ),
]

setup(name='polydim_pybind_v912', version='0.912', ext_modules=ext_modules)

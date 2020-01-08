from distutils.core import setup, Extension
from Cython.Build import cythonize
import numpy

extensions = [Extension(
				"reader",
				["reader.pyx"],
				extra_compile_args=['-fopenmp', '-g0'],
				extra_link_args=['-fopenmp'],
				include_dirs=[numpy.get_include()],
				language="c++"
			),
			Extension(
				"shared",
				["shared.pyx"],
				extra_compile_args=['-fopenmp', '-g0'],
				extra_link_args=['-fopenmp'],
				include_dirs=[numpy.get_include()]
			),
			Extension(
				"covariance_cy",
				["covariance_cy.pyx"],
				extra_compile_args=['-fopenmp', '-g0'],
				extra_link_args=['-fopenmp'],
				include_dirs=[numpy.get_include()]
			),
			Extension(
				"inbreed_cy",
				["inbreed_cy.pyx"],
				extra_compile_args=['-fopenmp', '-g0'],
				extra_link_args=['-fopenmp'],
				include_dirs=[numpy.get_include()]
			),
			Extension(
				"kinship_cy",
				["kinship_cy.pyx"],
				extra_compile_args=['-fopenmp', '-g0'],
				extra_link_args=['-fopenmp'],
				include_dirs=[numpy.get_include()]
			),
			Extension(
				"callGeno_cy",
				["callGeno_cy.pyx"],
				extra_compile_args=['-fopenmp', '-g0'],
				extra_link_args=['-fopenmp'],
				include_dirs=[numpy.get_include()]
			),
			Extension(
				"admixture_cy",
				["admixture_cy.pyx"],
				extra_compile_args=['-fopenmp', '-g0'],
				extra_link_args=['-fopenmp'],
				include_dirs=[numpy.get_include()]
			)]

setup(
	name="PCAngsd",
    ext_modules=cythonize(extensions),
    include_dirs=[numpy.get_include()]
)
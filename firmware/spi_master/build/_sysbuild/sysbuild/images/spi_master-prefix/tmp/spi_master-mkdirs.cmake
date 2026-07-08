# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file LICENSE.rst or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION ${CMAKE_VERSION}) # this file comes with cmake

# If CMAKE_DISABLE_SOURCE_CHANGES is set to true and the source directory is an
# existing directory in our source tree, calling file(MAKE_DIRECTORY) on it
# would cause a fatal error, even though it would be a no-op.
if(NOT EXISTS "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master")
  file(MAKE_DIRECTORY "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master")
endif()
file(MAKE_DIRECTORY
  "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master/build/spi_master"
  "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master/build/_sysbuild/sysbuild/images/spi_master-prefix"
  "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master/build/_sysbuild/sysbuild/images/spi_master-prefix/tmp"
  "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master/build/_sysbuild/sysbuild/images/spi_master-prefix/src/spi_master-stamp"
  "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master/build/_sysbuild/sysbuild/images/spi_master-prefix/src"
  "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master/build/_sysbuild/sysbuild/images/spi_master-prefix/src/spi_master-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master/build/_sysbuild/sysbuild/images/spi_master-prefix/src/spi_master-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/Users/fredrikwhaug/Desktop/cclosed/firmware/spi_master/build/_sysbuild/sysbuild/images/spi_master-prefix/src/spi_master-stamp${cfgdir}") # cfgdir has leading slash
endif()

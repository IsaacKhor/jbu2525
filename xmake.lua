add_rules('mode.debug', 'mode.release')
set_languages('c++23')
set_toolchains('llvm')

add_requires('fmt', 'rapidcsv', 'abseil')

target('build_plan', {
    set_kind('binary'),
    add_files('build_plan.cpp'),
    add_cxxflags('-Wall', '-Wextra'),
    add_packages('fmt', 'rapidcsv', 'abseil'),
})
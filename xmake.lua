add_rules('mode.debug', 'mode.releasedbg')
set_languages('c++23')
set_toolchains('llvm')

add_requires('fmt', 'rapidcsv', 'abseil')

target('graph_search', {
    set_kind('binary'),
    set_rundir(os.projectdir()),
    add_files('build_plan.cpp'),
    add_cxxflags('-Wall', '-Wextra'),
    add_packages('fmt', 'rapidcsv', 'abseil'),
    add_cxxflags('-fsanitize=address'),
    add_ldflags('-fsanitize=address'),
})

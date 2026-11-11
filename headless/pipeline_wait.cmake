# Bound PS5 pipeline-build synchronization objects (backported from ProsperoEden).
# Keep the replacement ABI-compatible with headers seen outside video_core.
foreach(pipeline_header IN ITEMS vk_graphics_pipeline.h vk_compute_pipeline.h)
    file(READ "${PROJECT_SOURCE_DIR}/src/video_core/renderer_vulkan/${pipeline_header}" pipeline_source)
    set(pipeline_wait_old "    std::condition_variable build_condvar;\n    std::mutex build_mutex;\n")
    string(FIND "${pipeline_source}" "${pipeline_wait_old}" pipeline_wait_at)
    if(pipeline_wait_at LESS 0)
        message(FATAL_ERROR "Pinned ${pipeline_header} build wait changed")
    endif()
    string(REPLACE "${pipeline_wait_old}"
        "    ::Eden::StripedCondition build_condvar;\n    ::Eden::StripedMutex build_mutex;\n"
        pipeline_source "${pipeline_source}")
    string(PREPEND pipeline_source "#include \"${EDEN_PORT_DIR}/striped_wait.h\"\n")
    write_derived("${PORT_BUILD_DIR}/pipeline-wait/video_core/renderer_vulkan/${pipeline_header}"
        "${pipeline_source}")
endforeach()
target_include_directories(video_core BEFORE PRIVATE "${PORT_BUILD_DIR}/pipeline-wait")

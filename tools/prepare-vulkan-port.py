"""Adapt the pinned Eden Vulkan platform boundary and required renderer fixes."""
from pathlib import Path
import struct
import subprocess
import sys
# --report: name every anchor that no longer matches (make update), instead of stopping at the first.
report = '--report' in sys.argv
source, output = map(Path, [a for a in sys.argv[1:] if a != '--report'])
port = Path(__file__).resolve().parents[1] / 'headless'
broken = []
def adapt(relative, destination, replacements):
    text = (source / relative).read_text()
    for old, new in replacements:
        if relative.endswith('/vk_rasterizer.cpp') and old.endswith('// update engine as channel may be different.') and old not in text:
            marker = '// Donkey Kong Bananza\'s terrain:'
            if marker in text:
                old = old.replace('// update engine as channel may be different.', marker)
                new = new.replace('// update engine as channel may be different.', marker)
        if relative.endswith('/vk_rasterizer.cpp') and old.startswith('    pipeline->SetEngine(maxwell3d, gpu_memory);') and old not in text:
            engine = '    pipeline->SetEngine(maxwell3d, gpu_memory);\n'
            configure = '    if (Profile::Scope scope{Profile::Zone::Configure}; !pipeline->Configure(is_indexed)) {'
            begin = text.index(engine) + len(engine)
            end = text.index(configure, begin)
            repack = text[begin:end]
            old = old.replace(engine, engine + repack)
            new = new.replace(configure, repack + configure)
        if relative.endswith('/vulkan_memory_allocator.cpp') and old.startswith('    vk::Check(vmaCreateBuffer(') and old not in text:
            if 'VkResult result = vmaCreateBuffer(' in text:
                # This core already retries outside the driver budget on allocation failure.
                if 'host_ci.flags &= ~VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT;' in text:
                    continue
        if text.count(old) != 1:
            if report:
                broken.append(f"{relative}: {old[:70]!r} (matches {text.count(old)})")
                continue
            raise RuntimeError(f"Pinned Vulkan anchor changed: {relative}: {old[:60]}")
        text = text.replace(old, new)
    path = output / destination
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text() != text:
        path.write_text(text)

adapt('src/core/frontend/emu_window.h', 'include/core/frontend/emu_window.h',
      [('    Xcb,', '    Xcb,\n    PS5,')])
adapt('src/video_core/renderer_vulkan/vk_rasterizer.cpp', 'vulkan_rasterizer.cpp', [
    # CounterEnable below starts a query immediately. A deferred clear has no
    # active pass yet, so later realization would end that query in a different
    # render-pass scope (VUID-vkCmdEndQuery-None-07007). Keep the immediate path
    # when the guest enables occlusion counting.
    ('const bool can_defer_clear = ENABLE_DEFERRED_CLEAR &&',
     'const bool can_defer_clear = ENABLE_DEFERRED_CLEAR && !regs.zpass_pixel_count_enable &&'),
    ('#include <algorithm>', '#include <algorithm>\n#include "performance.h"'),
    # Guest threads take the cache locks here (tracked-page writes, flush-area reads).
    ('bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {',
     'bool RasterizerVulkan::OnCPUWrite(DAddr addr, u64 size) {\n    ::Eden::Performance::Timer guest_write_timer(::Eden::Performance::guest_cpu_write);'),
    ('VideoCore::RasterizerDownloadArea RasterizerVulkan::GetFlushArea(DAddr addr, u64 size) {',
     'VideoCore::RasterizerDownloadArea RasterizerVulkan::GetFlushArea(DAddr addr, u64 size) {\n    ::Eden::Performance::Timer guest_read_timer(::Eden::Performance::guest_cpu_read);'),
    # ... and wait for those locks spinning briefly before sleeping (performance.h GuestCacheLock).
    ('        std::scoped_lock lock{texture_cache.mutex};\n        texture_area = texture_cache.GetFlushArea(addr, size);',
     '        ::Eden::Performance::GuestCacheLock(texture_cache.mutex);\n'
     '        std::lock_guard lock{texture_cache.mutex, std::adopt_lock};\n        texture_area = texture_cache.GetFlushArea(addr, size);'),
    ('        std::scoped_lock lock{buffer_cache.mutex};\n        if (buffer_cache.OnCPUWrite(addr, size)) {',
     '        ::Eden::Performance::GuestCacheLock(buffer_cache.mutex);\n'
     '        std::lock_guard lock{buffer_cache.mutex, std::adopt_lock};\n        if (buffer_cache.OnCPUWrite(addr, size)) {'),
    ('        std::scoped_lock lock{texture_cache.mutex};\n        texture_cache.WriteMemory(addr, size);\n    }\n    pipeline_cache.InvalidateRegion(addr, size);',
     '        ::Eden::Performance::GuestCacheLock(texture_cache.mutex);\n'
     '        std::lock_guard lock{texture_cache.mutex, std::adopt_lock};\n        texture_cache.WriteMemory(addr, size);\n    }\n    pipeline_cache.InvalidateRegion(addr, size);'),
    # Lichii submits by a policy of its own (submission_policy.h): Switch 2 titles every 128 draws,
    # the others every 4,096. 4,096 exceeds the PS5 GPU watchdog timeout in shader-heavy scenes
    # (VK_ERROR_DEVICE_LOST in Xenoblade 2's cities): 512 draws per submission there.
    ('    u32 legacy_budget = 4096;\n', '    u32 legacy_budget = 512;\n'),
    ('(device.IsMoltenVK() ? 128U : 4096U);', '(device.IsMoltenVK() ? 128U : 512U);'),
    # Where the ~4 us a draw spends goes: six phases under one running clock, each Mark taking the
    # gap since the previous one so they do not overlap. The Timer still wraps the whole function,
    # so a draw that returns early is charged for its unmarked tail and the sum of the six falls
    # short by that amount plus two clock reads per phase. control/scheduler.cpp aside, this is the
    # only place the dispatch's time can be spent - so its six numbers should add up to it.
    ('''    {
        Profile::Scope scope{Profile::Zone::FlushWork};
        FlushWork();
        gpu_memory->FlushCaching();
    }
''',
     '''    const ::Eden::Performance::Timer rasterizer_draw_timer(::Eden::Performance::rasterizer_draw);
    auto phase = ::Eden::Performance::MarkStart();
    {
        Profile::Scope scope{Profile::Zone::FlushWork};
        FlushWork();
        gpu_memory->FlushCaching();
    }
    ::Eden::Performance::Mark(::Eden::Performance::draw_flush, phase);
'''),
    ('''        return pipeline_cache.CurrentGraphicsPipeline();
    }()};
''',
     '''        return pipeline_cache.CurrentGraphicsPipeline();
    }()};
    ::Eden::Performance::Mark(::Eden::Performance::draw_pipeline, phase);
'''),
    ('''    // update engine as channel may be different.
    pipeline->SetEngine(maxwell3d, gpu_memory);
''',
     '''    // update engine as channel may be different.
    pipeline->SetEngine(maxwell3d, gpu_memory);
    // Waiting for both cache mutexes. SetEngine between them and here is two pointer assignments,
    // and the hold itself carries on through what follows: the phases below measure it.
    ::Eden::Performance::Mark(::Eden::Performance::draw_lock_wait, phase);
'''),
    ('''
    TrackOcarinaCamera();
    TrackOcarinaActor(pipeline->ShaderHashes()[1], is_indexed, is_indirect);
''',
     '''
    ::Eden::Performance::Mark(::Eden::Performance::draw_config, phase);
    TrackOcarinaCamera();
    TrackOcarinaActor(pipeline->ShaderHashes()[1], is_indexed, is_indirect);
'''),
    ('''    {
        Profile::Scope scope{Profile::Zone::DrawRecord};
''',
     '''    ::Eden::Performance::Mark(::Eden::Performance::draw_state, phase);
    {
        Profile::Scope scope{Profile::Zone::DrawRecord};
'''),
    ('''        draw_func();
    }
    submitted = true;
''',
     '''        draw_func();
    }
    ::Eden::Performance::Mark(::Eden::Performance::draw_record, phase);
    submitted = true;
'''),
    # A forced release blocks the GPU thread until the fence thread has retired
    # every older fence. Time only that producer-side drain.
    ('    fence_manager.WaitPendingFences(force);',
     '''    if (force) {
        ::Eden::Performance::Timer drain_timer(::Eden::Performance::gpu_fence_drain);
        fence_manager.WaitPendingFences(force);
    } else {
        fence_manager.WaitPendingFences(force);
    }'''),
    # The GPU thread, before it takes both cache locks for a draw: a guest thread asleep on one
    # goes first (performance.h YieldToGuests).
    ('    std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};\n    // What the next draw\'s TakeReusableDraw compares with',
     '    ::Eden::Performance::YieldToGuests();  // a guest thread asleep on a cache lock goes first\n'
     '    std::scoped_lock lock{buffer_cache.mutex, texture_cache.mutex};\n    // What the next draw\'s TakeReusableDraw compares with'),
    # Each draw counts toward the frame's busyness (headless/astc_policy.h: a CPU-converted ASTC
    # texture decodes in the background only in a busy frame). Its own anchor, apart from the
    # cache-lock hunk above, which other ports change.
    ('#include "video_core/texture_cache/texture_cache_base.h"',
     '#include "video_core/texture_cache/texture_cache_base.h"\n#include "astc_policy.h"'),
    ('    mesh_draw = pipeline->IsMeshPipeline();',
     '    ::Eden::AstcPolicy::Draw();\n    mesh_draw = pipeline->IsMeshPipeline();'),
])
# Host conditional rendering (VK_EXT_conditional_rendering, dev_vulkan.h hcr_mode): count each
# decision (EDEN_DEV_GUEST cond= slots 13-19); hcr=exact sends the conditions Eden would draw
# unconditionally, or predicate from a pending host query, to the exact CPU evaluation;
# hcr=cpu evaluates every condition on the CPU and predicates from constant 0/1 buffers.
adapt('src/video_core/renderer_vulkan/vk_query_cache.cpp', 'vulkan_query_cache.cpp', [
    ('#include "video_core/vulkan_common/vulkan_wrapper.h"\n',
     '#include "video_core/vulkan_common/vulkan_wrapper.h"\n#include "dev_vulkan.h"\n#include "performance.h"\n'),
    ('    vk::Buffer hcr_resolve_buffer;\n',
     '    vk::Buffer hcr_resolve_buffer;\n    vk::Buffer hcr_constant_buffer; // hcr=cpu: predicates 0 and 1\n'),
    ('        hcr_resolve_buffer = memory_allocator.CreateBuffer(buffer_ci, MemoryUsage::DeviceLocal);\n    }\n',
     '''        hcr_resolve_buffer = memory_allocator.CreateBuffer(buffer_ci, MemoryUsage::DeviceLocal);
        if (device.IsExtConditionalRendering() && ::Eden::DevVulkan::hcr_mode == 2) {
            VkBufferCreateInfo constant_ci = buffer_ci;
            constant_ci.size = 2 * sizeof(u32);
            constant_ci.usage = VK_BUFFER_USAGE_CONDITIONAL_RENDERING_BIT_EXT;
            hcr_constant_buffer = memory_allocator.CreateBuffer(constant_ci, MemoryUsage::Upload);
            const u32 predicates[2]{0, 1};
            std::memcpy(hcr_constant_buffer.Mapped().data(), predicates, sizeof(predicates));
            hcr_constant_buffer.Flush();
        }
    }
'''),
    ('bool QueryCacheRuntime::HostConditionalRenderingCompareValue(VideoCommon::LookupData object_1,\n',
     '''namespace {
// hcr=cpu: Maxwell3D::ProcessQueryCondition's exact evaluation (the read flushes pending GPU
// results), then the driver predicates the draws from a constant buffer. kind: 0 Conditional,
// 1 IfEqual, 2 IfNotEqual.
bool HostConditionalRenderingOnCpu(QueryCacheRuntime& runtime, QueryCacheRuntimeImpl& impl, DAddr address,
                                   unsigned kind) {
    if (address == 0 || !impl.hcr_constant_buffer) {
        ::Eden::Performance::CountCondition(13);
        runtime.EndHostConditionalRendering();
        return false;
    }
    u32 compare[6]{};
    impl.device_memory.ReadBlock(address, compare, sizeof(compare));
    const bool equal = compare[0] == compare[4] && compare[1] == compare[5];
    const bool execute = kind == 0 ? compare[0] != 0 && compare[1] != 0 : (kind == 1 ? equal : !equal);
    ::Eden::Performance::CountCondition(execute ? 17 : 18);
    const bool was_running = impl.is_hcr_running;
    if (was_running) {
        runtime.PauseHostConditionalRendering();
    }
    impl.hcr_setup.buffer = *impl.hcr_constant_buffer;
    impl.hcr_setup.offset = execute ? sizeof(u32) : 0;
    impl.hcr_setup.flags = 0;
    impl.hcr_is_set = true;
    impl.is_hcr_running = false;
    if (was_running) {
        runtime.ResumeHostConditionalRendering();
    }
    return true;
}
} // namespace

bool QueryCacheRuntime::HostConditionalRenderingCompareValue(VideoCommon::LookupData object_1,
'''),
    ('''        TraceConditionalRendering("extension-unavailable", false, object_1.address);
        return false;
    }
    HostConditionalRenderingCompareBCImpl(object_1.address, true, true);''',
     '''        TraceConditionalRendering("extension-unavailable", false, object_1.address);
        return false;
    }
    if (::Eden::DevVulkan::hcr_mode == 2) {
        return HostConditionalRenderingOnCpu(*this, *impl, object_1.address, 0);
    }
    if (::Eden::DevVulkan::hcr_mode == 1 && qc_dirty) {
        ::Eden::Performance::CountCondition(19);
        EndHostConditionalRendering();
        return false;
    }
    ::Eden::Performance::CountCondition(16);
    HostConditionalRenderingCompareBCImpl(object_1.address, true, true);'''),
    ('''        TraceConditionalRendering("extension-unavailable", false, object_1.address, object_2.address);
        return false;
    }

    const auto check_in_bc = [&](DAddr address) {''',
     '''        TraceConditionalRendering("extension-unavailable", false, object_1.address, object_2.address);
        return false;
    }
    if (::Eden::DevVulkan::hcr_mode == 2) {
        return HostConditionalRenderingOnCpu(*this, *impl, object_1.address, equal_check ? 1 : 2);
    }

    const auto check_in_bc = [&](DAddr address) {'''),
    ('''    if (!is_in_ac[0] && !is_in_ac[1]) {
        EndHostConditionalRendering();
        TraceConditionalRendering("uncached", false, object_1.address, object_2.address);
        return false;
    }

    if (!qc_dirty && !is_in_bc[0] && !is_in_bc[1]) {
        EndHostConditionalRendering();
        TraceConditionalRendering("guest-synchronized", false, object_1.address, object_2.address);
        return false;
    }
''',
     '''    if (!is_in_ac[0] && !is_in_ac[1]) {
        ::Eden::Performance::CountCondition(13);
        EndHostConditionalRendering();
        TraceConditionalRendering("uncached", false, object_1.address, object_2.address);
        return false;
    }

    if (!qc_dirty && !is_in_bc[0] && !is_in_bc[1]) {
        ::Eden::Performance::CountCondition(13);
        EndHostConditionalRendering();
        TraceConditionalRendering("guest-synchronized", false, object_1.address, object_2.address);
        return false;
    }
    // hcr=exact: a pending host query is not in any buffer yet; the CPU evaluation waits for it.
    if (::Eden::DevVulkan::hcr_mode == 1 && qc_dirty) {
        ::Eden::Performance::CountCondition(19);
        EndHostConditionalRendering();
        TraceConditionalRendering("exact-pending", false, object_1.address, object_2.address);
        return false;
    }
'''),
    ('''            HostConditionalRenderingCompareValueImpl(*objects[j], equal_check);
            TraceConditionalRendering(i == 0 ? "initial-zero" : "current-zero", true,''',
     '''            ::Eden::Performance::CountCondition(15);
            HostConditionalRenderingCompareValueImpl(*objects[j], equal_check);
            TraceConditionalRendering(i == 0 ? "initial-zero" : "current-zero", true,'''),
    ('''    if (!is_gpu_high) {
        EndHostConditionalRendering();
        TraceConditionalRendering("accuracy-bypass", true, object_1.address, object_2.address);
        return true;
    }

    if (!is_in_bc[0] && !is_in_bc[1]) {
        EndHostConditionalRendering();
        TraceConditionalRendering("query-cache-bypass", true, object_1.address, object_2.address);
        return true;
    }
    HostConditionalRenderingCompareBCImpl(object_1.address, equal_check);''',
     '''    // Eden draws these unconditionally; hcr=exact evaluates them on the CPU instead.
    if (!is_gpu_high || (!is_in_bc[0] && !is_in_bc[1])) {
        ::Eden::Performance::CountCondition(14);
        EndHostConditionalRendering();
        TraceConditionalRendering(!is_gpu_high ? "accuracy-bypass" : "query-cache-bypass",
                                  ::Eden::DevVulkan::hcr_mode != 1, object_1.address, object_2.address);
        return ::Eden::DevVulkan::hcr_mode != 1;
    }
    ::Eden::Performance::CountCondition(16);
    HostConditionalRenderingCompareBCImpl(object_1.address, equal_check);'''),
])
adapt('src/video_core/renderer_vulkan/vk_swapchain.cpp', 'vulkan_swapchain.cpp', [
    # An acquisition error has no usable image index. Forward it to the existing
    # renderer recovery path instead of indexing or presenting an invalid image.
    ('LOG_ERROR(Render_Vulkan, "vkAcquireNextImageKHR returned {}", string_VkResult(result));',
     'LOG_ERROR(Render_Vulkan, "vkAcquireNextImageKHR returned {}", string_VkResult(result));\n        vk::Check(result);'),
    ('LOG_CRITICAL(Render_Vulkan, "Failed to present with error {}", string_VkResult(result));',
     'LOG_CRITICAL(Render_Vulkan, "Failed to present with error {}", string_VkResult(result));\n        vk::Check(result);'),
])
# Keep the overlay in the existing display composition pass (also used for
# frontend screenshots), excluding guest applet captures. Cache its pipeline.
# Preserve upstream ABI, including consumers whose quoted includes resolve to
# the original header. Display/capture purpose belongs to the draw call.
adapt('src/video_core/present.h', 'include/video_core/present.h', [])
adapt('src/video_core/renderer_vulkan/vk_present_manager.h',
      'include/video_core/renderer_vulkan/vk_present_manager.h', [
    ('#include <mutex>', '#include <mutex>\n#include <exception>'),
    ('    std::jthread present_thread;',
     '    std::exception_ptr present_failure;\n    std::jthread present_thread;'),
])
adapt('src/video_core/renderer_vulkan/vk_present_manager.cpp', 'vulkan_present_manager.cpp', [
    ('#include "video_core/renderer_vulkan/vk_present_manager.h"',
     '#include "video_core/renderer_vulkan/vk_present_manager.h"\n#include "gpu_failure.h"\n#include "performance.h"'),
    # GetRenderFrame runs on the GPU thread: time its free-frame and
    # present-completion waits (FIFO back-pressure on the producer).
    ('    // Wait for free presentation frames\n    std::unique_lock lock{free_mutex};',
     '    // Wait for free presentation frames\n    ::Eden::Performance::Timer present_wait_timer(::Eden::Performance::gpu_present_wait);\n    std::unique_lock lock{free_mutex};'),
    ('PresentThread(token);', '''try {
            PresentThread(token);
        } catch (...) {
            const auto error = std::current_exception();
            {
                std::scoped_lock lock{queue_mutex, free_mutex};
                present_failure = error;
                present_queue.clear();
            }
            free_cv.notify_all();
            frame_cv.notify_all();
            Eden::RecordGpuFailure(error);
        }'''),
    ('free_cv.wait(lock, [this] { return !free_queue.empty(); });',
     '''free_cv.wait(lock, [this] { return present_failure || !free_queue.empty(); });
    if (present_failure) std::rethrow_exception(present_failure);'''),
    ('            present_queue.push_back(frame);',
     '            if (present_failure) return;\n            present_queue.push_back(frame);'),
    ('frame_cv.wait(queue_lock, [this] { return present_queue.empty(); });',
     'frame_cv.wait(queue_lock, [this] { return present_failure || present_queue.empty(); });'),
])
# Descriptor buffers: Eden's null buffer (nullDescriptor devices) has device address 0,
# but WriteDescriptorBuffer passed it with the binding's range. RADV then builds a real
# descriptor at GPU address 0; desktop kernels only log the resulting page fault, the PS5
# kills the title (TCP read at VA 0).
# The spec requires a null pAddressInfo (or VK_WHOLE_SIZE) for a null descriptor.
# The allocator's budget is the driver's, and on the console it does not say what is available: the
# driver counts each allocation twice (as VRAM and as visible VRAM), so the budget of the 8 GiB heap
# is used up at about 4 GiB, and it knows nothing of the pool the CPU shares. Eden asks for images
# and buffers within the budget and takes a refusal as final. A refused image or buffer is asked for
# again outside the budget; the driver refuses when the pool has no room, which is still the end of
# the session, and stderr.log then says what the pool had.
ALLOCATOR_REFUSED = """    VkResult created = CALL;
    if (created != VK_SUCCESS) {
        VmaAllocationCreateInfo outside_budget = alloc_ci;
        outside_budget.flags &= ~static_cast<VmaAllocationCreateFlags>(VMA_ALLOCATION_CREATE_WITHIN_BUDGET_BIT);
        created = AGAIN;
        static std::atomic<unsigned long long> refused{0};
        const auto times = refused.fetch_add(1, std::memory_order_relaxed) + 1;
        if ((times & (times - 1)) == 0) { // the 1st, 2nd, 4th, 8th ... time
            std::fprintf(stderr, "EDEN_GRAPHICS_MEMORY budget refused %llu requests; asked again outside it: result %d, DETAIL\\n",
                         times, int(created), VALUES);
        }
        if (created != VK_SUCCESS) {
            VmaBudget held[VK_MAX_MEMORY_HEAPS]{};
            vmaGetHeapBudgets(allocator, held);
            unsigned long long blocks = 0, used = 0;
            for (const VmaBudget& heap : held) {
                blocks += heap.statistics.blockBytes;
                used += heap.statistics.allocationBytes;
            }
            const auto free_block = ::Eden::Performance::graphics_memory_free.load(std::memory_order_relaxed);
            std::size_t guest_span = 0, guest_held = 0;
            ::Common::GuestMemoryUsage(&guest_span, &guest_held);
            std::fprintf(stderr, "EDEN_GRAPHICS_MEMORY refused outside the budget too (result %d): the pool's largest free "
                         "block is %llu MiB; the allocator holds %llu MiB in blocks, %llu MiB of it in use; the guest's "
                         "memory holds %llu MiB, the heap %llu MiB\\n",
                         int(created), free_block ? free_block() >> 20 : 0ull, blocks >> 20, used >> 20,
                         static_cast<unsigned long long>(guest_held >> 20),
                         static_cast<unsigned long long>(eden_heap_committed() >> 20));
            ::Eden::Performance::ReportHeap("a buffer was refused");
        }
    }
    vk::Check(created);
"""
def refused(call, detail, values):
    return (ALLOCATOR_REFUSED.replace('CALL', call).replace('AGAIN', call.replace('&alloc_ci', '&outside_budget'))
            .replace('DETAIL', detail).replace('VALUES', values))
IMAGE_VALUES = 'ci.extent.width, ci.extent.height, ci.extent.depth, ci.arrayLayers, ci.mipLevels, unsigned(ci.samples), int(ci.format)'
BUFFER_VALUES = 'static_cast<unsigned long long>(ci.size), unsigned(ci.usage)'
adapt('src/video_core/vulkan_common/vulkan_memory_allocator.h',
      'include/video_core/vulkan_common/vulkan_memory_allocator.h', [
    ('#pragma once', '#pragma once\n#include <array>\n#include <mutex>'),
    ('        vk::Image CreateImage(const VkImageCreateInfo &ci, bool dedicated = false) const;',
     '        vk::Image CreateImage(const VkImageCreateInfo &ci, bool dedicated = false) const;\n'
     '        vk::Image CreateTemporaryImage(const VkImageCreateInfo &ci) const;'),
    ('        u32 valid_memory_types{~0u};',
     '        u32 valid_memory_types{~0u};\n'
     '        mutable std::mutex temporary_pool_mutex;\n'
     '        mutable std::array<VmaPool, VK_MAX_MEMORY_TYPES> temporary_pools{};'),
])
adapt('src/video_core/vulkan_common/vulkan_memory_allocator.cpp', 'vulkan_memory_allocator.cpp', [
    ('vk::Image MemoryAllocator::CreateUnbackedImage(const VkImageCreateInfo &ci, bool aliased) const {',
     (port / 'transient_images.inc').read_text() + '\nvk::Image MemoryAllocator::CreateUnbackedImage(const VkImageCreateInfo &ci, bool aliased) const {'),
    ('MemoryAllocator::MemoryAllocator(const Device &device_)',
     r'''namespace {
std::mutex vma_probe_mutex;
VmaAllocator vma_probe_allocator{};
void EdenVmaSnapshot(VmaAllocator allocator, unsigned tag) {
    char* json = nullptr;
    vmaBuildStatsString(allocator, &json, VK_TRUE);
    if (!json) return;
    char path[192];
    std::snprintf(path, sizeof(path), "/data/eglantineps5/logs/mkw-vma-%d-%u.json", getpid(), tag);
    const auto bytes = std::strlen(json);
    bool written = false;
    if (bytes <= (8U << 20)) {
        if (FILE* file = std::fopen(path, "w")) {
            written = std::fwrite(json, 1, bytes, file) == bytes;
            std::fclose(file);
        }
    }
    std::fprintf(stderr, "MKW_VMA_MAP tag=%u bytes=%zu written=%u\n", tag, bytes, unsigned(written));
    vmaFreeStatsString(allocator, json);
}
}
extern "C" void eden_vma_probe(unsigned seconds) {
    std::lock_guard lock{vma_probe_mutex};
    if (vma_probe_allocator) EdenVmaSnapshot(vma_probe_allocator, 100000 + seconds);
}
MemoryAllocator::MemoryAllocator(const Device &device_)'''),
    ('    // Preserve the previous "RenderDoc small heap"',
     '    { std::lock_guard lock{vma_probe_mutex}; vma_probe_allocator = allocator; }\n'
     '    // Preserve the previous "RenderDoc small heap"'),
    ('MemoryAllocator::~MemoryAllocator() = default;',
     'MemoryAllocator::~MemoryAllocator() {\n'
     '    std::lock_guard lock{vma_probe_mutex};\n'
     '    if (vma_probe_allocator == allocator) vma_probe_allocator = nullptr;\n'
     '    for (auto pool : temporary_pools) if (pool) vmaDestroyPool(allocator, pool);\n' +
     ('    DestroySparsePools();\n' if 'DestroySparsePools' in (source / 'src/video_core/vulkan_common/vulkan_memory_allocator.h').read_text() else '') +
     '}'),
    ('#include "video_core/vulkan_common/vulkan_memory_allocator.h"\n',
     '#include "video_core/vulkan_common/vulkan_memory_allocator.h"\n#include <atomic>\n#include <cstddef>\n#include <cstdio>\n#include <cstring>\n#include <cstdlib>\n#include "performance.h"\nnamespace Common { void GuestMemoryUsage(std::size_t* span, std::size_t* held) noexcept; }\nextern "C" std::size_t eden_heap_committed(void);\n'),
    # An image with nothing bound (the sparse virtual texture arrays no pool could hold): when the driver refuses
    # it with residency, it is asked for again with binding alone, and what it said is written down.
    ('    if (device.GetDispatchLoader().vkCreateImage(*device.GetLogical(), &sparse_ci, nullptr,\n'
     '                                                 &sparse) != VK_SUCCESS) {\n'
     '        return vk::Image{};\n'
     '    }\n',
     """    VkResult sparse_result = device.GetDispatchLoader().vkCreateImage(*device.GetLogical(), &sparse_ci, nullptr, &sparse);
    if (sparse_result != VK_SUCCESS) {
        VkImageCreateInfo binding_only = ci;
        binding_only.flags |= VK_IMAGE_CREATE_SPARSE_BINDING_BIT;
        const VkResult second = device.GetDispatchLoader().vkCreateImage(*device.GetLogical(), &binding_only, nullptr, &sparse);
        std::fprintf(stderr, "EDEN_SPARSE_IMAGE %ux%ux%u, %u layers, %u levels, format %d, usage 0x%x, flags 0x%x, tiling %d: "
                     "with residency %d, binding alone %d\\n",
                     ci.extent.width, ci.extent.height, ci.extent.depth, ci.arrayLayers, ci.mipLevels, int(ci.format),
                     unsigned(ci.usage), unsigned(ci.flags), int(ci.tiling), int(sparse_result), int(second));
        if (second != VK_SUCCESS) {
            // Once: which smaller sizes does the driver accept? Each probe is made and destroyed at once.
            static std::atomic<bool> probed{false};
            if (!probed.exchange(true)) {
                for (u32 layers = ci.arrayLayers / 2; layers >= 1; layers /= 2) {
                    VkImageCreateInfo probe = sparse_ci;
                    probe.arrayLayers = layers;
                    VkImage probe_image{};
                    const VkResult probed_result =
                        device.GetDispatchLoader().vkCreateImage(*device.GetLogical(), &probe, nullptr, &probe_image);
                    std::fprintf(stderr, "EDEN_SPARSE_PROBE %u layers: %d\\n", layers, int(probed_result));
                    if (probed_result == VK_SUCCESS) {
                        device.GetDispatchLoader().vkDestroyImage(*device.GetLogical(), probe_image, nullptr);
                    }
                    if (layers == 1) break;
                }
            }
            return vk::Image{};
        }
    }
"""),
    ('    vk::Check(vmaCreateBufferWithAlignment(allocator, &ci, &alloc_ci, min_alignment, &handle,\n'
     '                                           &allocation, &alloc_info));\n',
     refused('vmaCreateBufferWithAlignment(allocator, &ci, &alloc_ci, min_alignment, &handle,\n'
             '                                           &allocation, &alloc_info)',
             'buffer of %llu bytes, usage 0x%x', BUFFER_VALUES)),
])
# Staging buffers (headless/staging_buffers.h): above 16 MiB a buffer the CPU writes or reads is its
# transfer rounded up to 16 MiB instead of the next power of two, a kept buffer is handed out again
# only when it holds the transfer, and a refused buffer is asked for once more after the kept ones
# the GPU is done with are let go. A Switch 2 title was refused 512 MiB for a 341 MiB transfer with
# 480 MiB free. No Finish() when releasing: a buffer handed out earlier may not have its copy recorded.
adapt('src/video_core/renderer_vulkan/vk_staging_buffer_pool.h',
      'include/video_core/renderer_vulkan/vk_staging_buffer_pool.h', [
    ('    void TickFrame();\n', '    void TickFrame();\n    void ReleaseCompleted();\n'),
])
adapt('src/video_core/renderer_vulkan/vk_staging_buffer_pool.cpp', 'vulkan_staging_buffer_pool.cpp', [
    ('StagingBufferRef StagingBufferPool::CreateStagingBuffer(size_t size, MemoryUsage usage, bool deferred) {',
     '''StagingBufferRef StagingBufferPool::CreateStagingBuffer(size_t size, MemoryUsage usage, bool deferred) {
    if (static unsigned rows{}; size >= (64ULL << 20) && rows++ < 96) {
        for (unsigned kind = 0; kind < 3; ++kind) {
            auto& cache = kind == 0 ? device_local_cache : kind == 1 ? upload_cache : download_cache;
            size_t count = 0, pinned = 0, busy = 0, free = 0;
            unsigned long long bytes = 0;
            for (const auto& level : cache) for (const auto& entry : level.entries) {
                ++count;
                bytes += ::Eden::StagingBuffers::Holds(entry.mapped_span.size(), entry.log2_level);
                if (entry.deferred) ++pinned;
                else if (scheduler.IsFree(entry.tick)) ++free;
                else ++busy;
            }
            std::fprintf(stderr, "MKW_STAGING_MISS asked=%zu usage=%u deferred=%d kind=%u count=%zu bytes=%llu pinned=%zu busy=%zu free=%zu tick=%llu completed=%llu\\n",
                         size, unsigned(usage), int(deferred), kind, count, bytes, pinned, busy, free,
                         static_cast<unsigned long long>(scheduler.CurrentTick()),
                         static_cast<unsigned long long>(scheduler.GetMasterSemaphore().KnownGpuTick()));
        }
    }
'''),
    ('#include "video_core/vulkan_common/vulkan_wrapper.h"\n',
     '#include "video_core/vulkan_common/vulkan_wrapper.h"\n#include <atomic>\n#include <cstdio>\n#include "performance.h"\n#include "staging_buffers.h"\n'),
    # While the console's pool is short, every staging buffer the GPU is done with goes back at the
    # frame's end. Eden frees them slowly - one size class a frame, 16 buffers at most, so a buffer
    # can stay 64 frames after its last use - and a course loading in Mario Kart World stages its
    # textures a layer at a time: the buffers it left behind held the pool its next request needed.
    # (ProsperoEden's TickFrame release; ReleaseCompleted is the same walk the transcode path uses.)
    ('    ReleaseCache(MemoryUsage::Download);\n}',
     '    ReleaseCache(MemoryUsage::Download);\n'
     '    if (::Eden::Performance::GraphicsMemoryIsShort()) {\n'
     '        ReleaseCompleted();\n'
     '    }\n'
     '}'),
    ('void StagingBufferPool::TickFrame() {',
     'void StagingBufferPool::ReleaseCompleted() {\n'
     '    const auto idle = [this](const StagingBuffer& entry) {\n'
     '        return !entry.deferred && scheduler.IsFree(entry.tick);\n'
     '    };\n'
     '    for (StagingBuffersCache* const cache : {&device_local_cache, &upload_cache, &download_cache}) {\n'
     '        for (StagingBuffers& level : *cache) {\n'
     '            ::Eden::StagingBuffers::ReleaseFrom(level, idle);\n'
     '        }\n'
     '    }\n'
     '}\n\nvoid StagingBufferPool::TickFrame() {'),
    ('    const auto is_free = [this](const StagingBuffer& entry) {\n'
     '        return !entry.deferred && scheduler.IsFree(entry.tick);\n'
     '    };',
     '    const auto is_free = [this, size](const StagingBuffer& entry) {\n'
     '        return !entry.deferred && scheduler.IsFree(entry.tick) &&\n'
     '               ::Eden::StagingBuffers::Holds(entry.mapped_span.size(), entry.log2_level) >= size;\n'
     '    };'),
    ('    auto const log2_size = Common::Log2Ceil<u32>(u32(size));\n',
     '    auto const log2_size = Common::Log2Ceil<u32>(u32(size));\n'
     '    const bool exact = ::Eden::StagingBuffers::Exact(size, usage != MemoryUsage::DeviceLocal);\n'
     '    const VkDeviceSize made = ::Eden::StagingBuffers::Size(size, log2_size, exact);\n'
     '    if (exact) {\n'
     '        // Kept buffers of this power of two too small for the transfer go before it is made.\n'
     '        ::Eden::StagingBuffers::ReleaseFrom(GetCache(usage)[log2_size], [this, size](const StagingBuffer& entry) {\n'
     '            return !entry.deferred && scheduler.IsFree(entry.tick) &&\n'
     '                   ::Eden::StagingBuffers::Holds(entry.mapped_span.size(), entry.log2_level) < size;\n'
     '        });\n'
     '    }\n'),
    ('        .size = 1ULL << log2_size,\n', '        .size = made,\n'),
    ('    vk::Buffer buffer = memory_allocator.CreateBuffer(buffer_ci, usage);\n',
     '    vk::Buffer buffer;\n'
     '    try {\n'
     '        buffer = memory_allocator.CreateBuffer(buffer_ci, usage);\n'
     '    } catch (const vk::Exception& refused) {\n'
     '        if (refused.GetResult() != VK_ERROR_OUT_OF_DEVICE_MEMORY) {\n'
     '            throw;\n'
     '        }\n'
     '        // Refused: the kept buffers the GPU is done with go, and the buffer is asked for once\n'
     '        // more. Refused again, the error goes on as before.\n'
     '        const auto idle = [this](const StagingBuffer& entry) {\n'
     '            return !entry.deferred && scheduler.IsFree(entry.tick);\n'
     '        };\n'
     '        ::Eden::StagingBuffers::Released released;\n'
     '        for (StagingBuffersCache* const cache : {&device_local_cache, &upload_cache, &download_cache}) {\n'
     '            for (StagingBuffers& level : *cache) {\n'
     '                released += ::Eden::StagingBuffers::ReleaseFrom(level, idle);\n'
     '            }\n'
     '        }\n'
     '        std::fprintf(stderr, "EDEN_STAGING_OOM asked=%zu made=%llu released=%zu buffers (%llu MiB)\\n", size,\n'
     '                     static_cast<unsigned long long>(made), released.buffers,\n'
     '                     static_cast<unsigned long long>(released.bytes >> 20));\n'
     '        buffer = memory_allocator.CreateBuffer(buffer_ci, usage);\n'
     '    }\n'
     '    // A large buffer smaller than the power of two: the 1st, 2nd, 4th, 8th ... in the log.\n'
     '    if (exact && made >= (VkDeviceSize{64} << 20) && made < (VkDeviceSize{1} << log2_size)) {\n'
     '        static std::atomic<unsigned long long> large{0};\n'
     '        const auto times = large.fetch_add(1, std::memory_order_relaxed) + 1;\n'
     '        if ((times & (times - 1)) == 0) {\n'
     '            std::fprintf(stderr, "EDEN_STAGING_EXACT %llu MiB made for a transfer of %llu MiB, not the %llu MiB of the "\n'
     '                         "next power of two (%llu so far)\\n",\n'
     '                         static_cast<unsigned long long>(made >> 20), static_cast<unsigned long long>(size >> 20),\n'
     '                         static_cast<unsigned long long>((VkDeviceSize{1} << log2_size) >> 20), times);\n'
     '        }\n'
     '    }\n'),
])
# The software blitter: Lichii gives its large scratch buffers back after each blit itself
# (ReleaseLargeBuffers), so the copy the build compiles (headless/vulkan.cmake) is unchanged.
adapt('src/video_core/engines/sw_blitter/blitter.cpp', 'sw_blitter.cpp', [])
# Development A/B switches for device features (headless/dev_vulkan.h, dev-settings).
adapt('src/video_core/vulkan_common/vulkan_device.cpp', 'vulkan_device.cpp', [
    # The allocator counts what it holds itself instead of asking the driver. The driver's figures
    # are wrong on the console: it counts each allocation of graphics memory twice (as VRAM and as
    # visible VRAM), so the allocator saw the budget of the 8 GiB heap used up at 4 GiB. From there
    # it could make no more of its blocks and gave every image memory of its own: 926 allocations
    # where 40 blocks had done, a third of what it held unused (1.3 of 3.9 GiB in a large open-world
    # game at 2x), and the shared pool cut into hundreds of pieces. Without the driver's budget its
    # own count stands against four fifths of the heap. Only VMA's view changes: the caches' usage
    # and budget (GetDeviceMemoryUsage/GetDeviceMemoryBudget below) still read the extension or the
    # pool, and vmaGetHeapBudgets' statistics are VMA's own either way. A request past VMA's
    # four fifths is still asked for again outside the budget (ALLOCATOR_REFUSED above and Eglantine's
    # relaxed retries); with the double count gone that retry is the rare path it was meant to be.
    ('    if (extensions.memory_budget) {\n        flags |= VMA_ALLOCATOR_CREATE_EXT_MEMORY_BUDGET_BIT;\n    }\n',
     '    // The driver\'s budget is not asked for: its count is double (tools/prepare-vulkan-port.py).\n'),
    ('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include "dev_vulkan.h"\n#include "performance.h"'),
    # "Memory in use" for the texture and buffer caches: on the console, the budget less what is
    # left of the pool the CPU shares with the GPU (performance.h, graphics_memory_free).
    ('u64 Device::GetDeviceMemoryUsage() const {\n',
     'namespace {\n'
     '// The largest block of the shared pool that was free when the device was made: about the most\n'
     '// graphics can be given in this session.\n'
     'u64 graphics_capacity = 0;\n'
     '}\n\n'
     'u64 Device::GetDeviceMemoryUsage() const {\n'
     '    if (const auto free_memory = ::Eden::Performance::graphics_memory_free.load(std::memory_order_relaxed);\n'
     '        free_memory && ::Eden::Performance::graphics_usage_from_pool.load(std::memory_order_relaxed)) {\n'
     '        // The caches evict what is unused 1.6 GiB under the budget and evict hard 0.8 GiB under\n'
     '        // it. Where the pool could never give graphics 6.4 GiB, those marks become a quarter\n'
     '        // and an eighth of what it could give.\n'
     '        const double scale = graphics_capacity != 0 && graphics_capacity < 6400_MiB\n'
     '                                 ? static_cast<double>(6400_MiB) / static_cast<double>(graphics_capacity)\n'
     '                                 : 1.0;\n'
     '        const u64 free_bytes = static_cast<u64>(static_cast<double>(free_memory()) * scale);\n'
     '        return device_access_memory > free_bytes ? device_access_memory - free_bytes : 0;\n'
     '    }\n'),
    # Usage above is expressed against device_access_memory, not the driver's
    # changing heap budget. Keep both sides of the cache's pressure comparison
    # in that same domain; the shared-pool free callback already reflects CPU
    # allocations and fragmentation.
    ('u64 Device::GetDeviceMemoryBudget() const {\n',
     'u64 Device::GetDeviceMemoryBudget() const {\n'
     '    if (::Eden::Performance::graphics_memory_free.load(std::memory_order_relaxed) &&\n'
     '        ::Eden::Performance::graphics_usage_from_pool.load(std::memory_order_relaxed)) {\n'
     '        return device_access_memory;\n'
     '    }\n'),
    ('    extensions.descriptor_buffer = features.descriptor_buffer.descriptorBuffer;',
     '    extensions.descriptor_buffer = features.descriptor_buffer.descriptorBuffer &&\n'
     '        !::Eden::DevVulkan::disable_descriptor_buffer;'),
    ('    features.robustness2.robustBufferAccess2 = VK_FALSE;\n'
     '    features.robustness2.robustImageAccess2 = VK_FALSE;\n'
     '    extensions.robustness_2 = features.robustness2.nullDescriptor;',
     '    if (!::Eden::DevVulkan::robustness2) {\n'
     '        features.robustness2.robustBufferAccess2 = VK_FALSE;\n'
     '        features.robustness2.robustImageAccess2 = VK_FALSE;\n'
     '    }\n'
     '    if (::Eden::DevVulkan::disable_null_descriptor) {\n'
     '        features.robustness2.nullDescriptor = VK_FALSE;\n'
     '    }\n'
     '    extensions.robustness_2 = features.robustness2.nullDescriptor;'),
    ('            (queue_family_properties[*graphics].queueFlags & VK_QUEUE_SPARSE_BINDING_BIT) != 0;',
     '            (queue_family_properties[*graphics].queueFlags & VK_QUEUE_SPARSE_BINDING_BIT) != 0 &&\n'
     '            !::Eden::DevVulkan::disable_sparse;'),
    ('            features.custom_border_color.customBorderColorWithoutFormat;\n    }\n'
     '    RemoveExtensionFeatureIfUnsuitable(extensions.custom_border_color',
     '            features.custom_border_color.customBorderColorWithoutFormat &&\n'
     '            !::Eden::DevVulkan::disable_custom_border;\n    }\n'
     '    RemoveExtensionFeatureIfUnsuitable(extensions.custom_border_color'),
    # dev-settings conditional_rendering=off: guest render-enable conditions are resolved
    # without VK_EXT_conditional_rendering (the path Eden takes on drivers without it).
    ('    // VK_EXT_border_color_swizzle\n',
     '    if (::Eden::DevVulkan::disable_conditional_rendering) {\n'
     '        extensions.conditional_rendering = false;\n    }\n'
     '    // VK_EXT_border_color_swizzle\n'),
    # The heaps and the budget the texture/buffer caches size themselves from.
    ('            device_access_memory = std::min<u64>(device_access_memory, normal_memory + scaler_memory);\n'
     '        }\n    }\n}\n',
     '            device_access_memory = std::min<u64>(device_access_memory, normal_memory + scaler_memory);\n'
     '        }\n    }\n'
     '    if (const auto free_memory = ::Eden::Performance::graphics_memory_free.load(std::memory_order_relaxed)) {\n'
     '        graphics_capacity = free_memory();\n'
     '    }\n'
     '    std::printf("EDEN_VULKAN_MEMORY integrated=%d heaps=%zu local=%llu initial_usage=%llu device_access=%llu "\n'
     '                "capacity=%llu\\n",\n'
     '                int(is_integrated), valid_heap_memory.size(), static_cast<unsigned long long>(local_memory),\n'
     '                static_cast<unsigned long long>(device_initial_usage),\n'
     '                static_cast<unsigned long long>(device_access_memory),\n'
     '                static_cast<unsigned long long>(graphics_capacity));\n}\n'),
])
# Development GPU fault probe (dev_vulkan.h, submit_sync=on): wait for every
# submission, so the CPU never records against work the GPU has not finished.
GPU_TIME_HELPERS = (port / 'gpu_time_probe.inc').read_text()
# Keep command availability separate from queue-drain completion. Only the worker
# waits on event_cv; WaitWorker waits on drain_cv under the same queue mutex.
adapt('src/video_core/renderer_vulkan/vk_scheduler.h',
      'include/video_core/renderer_vulkan/vk_scheduler.h', [
    ('    std::condition_variable_any event_cv;',
     '    std::condition_variable_any event_cv;\n    std::condition_variable drain_cv;\n    unsigned drain_waiters{};'),
])
adapt('src/video_core/renderer_vulkan/vk_scheduler.cpp', 'vulkan_scheduler.cpp', [
    # Lichii's destructor stops the worker only when its GPU trace is on; the port's timing queries
    # need it stopped in every case before they go.
    ('''Scheduler::~Scheduler() {
    if (trace_query_pool) {
        WaitWorker();
        worker_thread.request_stop();
        worker_thread.join();
        if (trace_gpu_tick != 0) {
            master_semaphore->Wait(trace_gpu_tick);
        }
    }
}''',
     '''Scheduler::~Scheduler() {
    if (trace_query_pool) {
        WaitWorker();
    }
    worker_thread.request_stop();
    if (worker_thread.joinable()) worker_thread.join();
    if (trace_query_pool && trace_gpu_tick != 0) {
        master_semaphore->Wait(trace_gpu_tick);
    }
    GpuTimeReset(device);
}'''),
    ('        event_cv.wait(ql, [this] { return work_queue.empty(); });',
     '        ++drain_waiters;\n        drain_cv.wait(ql, [this] { return work_queue.empty(); });\n        --drain_waiters;'),
    ('            event_cv.notify_all();', '            if (eden_vulkan_handoff_enabled()) event_cv.notify_one();\n            else event_cv.notify_all();'),
    ('        work_queue.pop();\n        event_cv.notify_all();',
     '        work_queue.pop();\n        if (!eden_vulkan_handoff_enabled() || (work_queue.empty() && drain_waiters)) drain_cv.notify_all();'),

    ('#include <memory>', '#include <memory>\n#include <array>\n#include <chrono>\n#include <cstdio>\n#include "dev_vulkan.h"\n#include "hud_gpu_time.h"\n#include "submission_origin.h"\nextern "C" bool eden_vulkan_handoff_enabled();'),
    ('namespace Vulkan {\n', 'namespace Vulkan {\n' + GPU_TIME_HELPERS),
    ('        .pInheritanceInfo = nullptr,\n    });\n    if (trace_query_pool && !trace_gpu_failed',
     '        .pInheritanceInfo = nullptr,\n    });\n    GpuTimeBegin(device, current_upload_cmdbuf);\n    if (trace_query_pool && !trace_gpu_failed'),
    ('u64 Scheduler::Flush(VkSemaphore signal_semaphore, VkSemaphore wait_semaphore,\n                     std::source_location location) {',
     'u64 Scheduler::Flush(VkSemaphore signal_semaphore, VkSemaphore wait_semaphore,\n                     std::source_location location) {\n'
     '    GpuSubmitOriginScope origin{__builtin_return_address(0), false, true};'),
    ('void Scheduler::Finish(VkSemaphore signal_semaphore, VkSemaphore wait_semaphore,\n                       std::source_location location) {',
     'void Scheduler::Finish(VkSemaphore signal_semaphore, VkSemaphore wait_semaphore,\n                       std::source_location location) {\n'
     '    GpuSubmitOriginScope origin{__builtin_return_address(0), true, true};'),
    ('    RecordWithUploadBuffer([signal_semaphore, wait_semaphore, signal_value,',
     '    RecordWithUploadBuffer([signal_semaphore, wait_semaphore, signal_value,\n'
     '                            submit_origin = gpu_submit_origin,'),
    ('        cmdbuf.End();\n\n        if (on_submit)',
     '        GpuTimeEnd(cmdbuf);\n        cmdbuf.End();\n\n        if (on_submit)'),
    ('            vk::Check(result);\n            break;\n        }\n        if (trace_frame_end != 0) {',
     '            vk::Check(result);\n            break;\n        }\n'
     '        GpuTimeCountOrigin(submit_origin);\n        GpuTimeCollect(device);\n        if (trace_frame_end != 0) {'),
    ('    const u64 signal_value = SubmitExecution(signal_semaphore, wait_semaphore);\n'
     '    AllocateNewContext();\n    submitted_serial = record_serial;',
     '    const u64 signal_value = SubmitExecution(signal_semaphore, wait_semaphore);\n'
     '    if (::Eden::DevVulkan::sync_submissions) {\n        Wait(signal_value);\n    }\n'
     '    AllocateNewContext();\n    submitted_serial = record_serial;'),
])
adapt('src/video_core/renderer_vulkan/pipeline_helper.h',
      'include/video_core/renderer_vulkan/pipeline_helper.h', [
    ('            VkDescriptorGetInfoEXT get_info{',
     '            const VkDescriptorAddressInfoEXT* const buffer_info{\n'
     '                entry.address.address != 0 ? &address_info : nullptr};\n'
     '            VkDescriptorGetInfoEXT get_info{'),
    ('get_info.data.pUniformBuffer = &address_info;', 'get_info.data.pUniformBuffer = buffer_info;'),
    ('get_info.data.pStorageBuffer = &address_info;', 'get_info.data.pStorageBuffer = buffer_info;'),
    ('get_info.data.pUniformTexelBuffer = &address_info;', 'get_info.data.pUniformTexelBuffer = buffer_info;'),
    ('get_info.data.pStorageTexelBuffer = &address_info;', 'get_info.data.pStorageTexelBuffer = buffer_info;'),
])
adapt('src/video_core/renderer_vulkan/vk_blit_screen.h',
      'include/video_core/renderer_vulkan/vk_blit_screen.h', [
    ('VkFormat current_swapchain_view_format, const HdrPresent& output = {});',
     'VkFormat current_swapchain_view_format, const HdrPresent& output = {}, bool draw_hud = false);'),
])
adapt('src/video_core/renderer_vulkan/renderer_vulkan.h',
      'include/video_core/renderer_vulkan/renderer_vulkan.h', [
    ('    void Composite(', '    void PresentLoading();\n    void Composite('),
])
adapt('src/video_core/renderer_vulkan/renderer_vulkan.cpp', 'vulkan_renderer.cpp', [
    ('#include "video_core/renderer_vulkan/renderer_vulkan.h"',
     '#include "video_core/renderer_vulkan/renderer_vulkan.h"\n#include "display_refresh.h"\n'
     '#include "diagnostics.h"\n#include "hud.h"'),
    # The HUD counted the guest rate only: OnFrameDisplayed() runs once per Composite(), while the
    # frames frame generation adds are presented through PresentManager::Present() (hud.h). Count
    # every frame handed to the present manager.
    ('            present_manager.Present(generated);\n',
     '            present_manager.Present(generated);\n'
     '            Eden::CountPresentedFrame();\n'),
    # A frame the display has no refresh for is not presented: a game patched for more frames
    # than the output shows keeps its pace instead of waiting for a refresh per frame
    # (headless/display_refresh.h). The frame still ends as any other.
    ('    RenderScreenshot(framebuffers);\n    const auto acquiring = trace',
     '    RenderScreenshot(framebuffers);\n'
     '    if (::Eden::Display::SkipFrame()) {\n'
     '        gpu.RendererFrameEndNotify();\n'
     '        rasterizer.TickFrame();\n'
     '        return;\n'
     '    }\n'
     '    const auto acquiring = trace'),
    ('    Report();', '    PresentLoading();\n    Report();'),
    ('present_manager.SwapchainImageCount(), output_format.format, output);',
     'present_manager.SwapchainImageCount(), output_format.format, output, true);'),
    ('framebuffers, layout, 1, format,\n                             CaptureHdrPresent());',
     'framebuffers, layout, 1, format,\n                             CaptureHdrPresent(), true);'),
    ('void RendererVulkan::Report() const {',
     (port / 'vulkan_loading.inc').read_text() + '\nvoid RendererVulkan::Report() const {'),
    # Present() only records the hand-off into a fresh chunk. Dispatch it now so
    # the present thread gets this frame immediately instead of after the
    # producer's next 8-draw dispatch (upstream does this only with LSFG).
    ('        present_manager.Present(frame);\n    }\n',
     '        present_manager.Present(frame);\n        Eden::CountPresentedFrame();\n    }\n'),
    ('                                 : std::chrono::steady_clock::time_point{};\n#ifdef HAS_LSFG\n    scheduler.DispatchWork();\n#endif',
     '                                 : std::chrono::steady_clock::time_point{};\n    scheduler.DispatchWork();'),
    ('} // namespace Vulkan', '''} // namespace Vulkan
namespace Eden {
void PresentVulkanLoading(VideoCore::RendererBase& renderer) {
    static_cast<Vulkan::RendererVulkan&>(renderer).PresentLoading();
}
}'''),
])
adapt('src/video_core/renderer_vulkan/present/window_adapt_pass.h',
      'include/video_core/renderer_vulkan/present/window_adapt_pass.h', [
    ('              VkExtent2D extent, const HdrPresent& output);',
     '              VkExtent2D extent, const HdrPresent& output, bool draw_hud = false);'),
    ('    vk::Pipeline coverage_pipeline;',
     '    vk::Pipeline coverage_pipeline;\n    vk::PipelineLayout hud_layout;\n    vk::Pipeline hud_pipeline;'),
])
adapt('src/video_core/renderer_vulkan/present/window_adapt_pass.cpp', 'vulkan_window_adapt_pass.cpp', [
    ('#include "core/frontend/framebuffer_layout.h"',
     '#include "core/frontend/framebuffer_layout.h"\n#include "hud.h"\n#include "vulkan_hud_shaders.h"'),
    ('                           VkFramebuffer framebuffer, VkExtent2D extent,\n                           const HdrPresent& output) {',
     '                           VkFramebuffer framebuffer, VkExtent2D extent,\n                           const HdrPresent& output, bool draw_hud) {'),
    ('    scheduler.Record([=](vk::CommandBuffer cmdbuf) {',
     (port / 'vulkan_hud_prepare.inc').read_text() + '\n    scheduler.Record([=](vk::CommandBuffer cmdbuf) {'),
    ('        cmdbuf.EndRenderPass();',
     (port / 'vulkan_hud_draw.inc').read_text() + '\n        cmdbuf.EndRenderPass();'),
])
adapt('src/video_core/renderer_vulkan/vk_blit_screen.cpp', 'vulkan_blit_screen.cpp', [
    ('                             VkFormat current_swapchain_view_format, const HdrPresent& output) {',
     '                             VkFormat current_swapchain_view_format, const HdrPresent& output, bool draw_hud) {'),
    # The HUD goes on the SDR path; the HDR composite is drawn without it.
    ('                           *frame->framebuffer, VkExtent2D{frame->width, frame->height}, output);',
     '                           *frame->framebuffer, VkExtent2D{frame->width, frame->height}, output, draw_hud);'),
])
shader_header = '#pragma once\n#include <cstdint>\n'
for stage in ('vert', 'frag'):
    binary = output / f'vulkan_hud.{stage}.spv'
    subprocess.run(['glslangValidator', '-V', '--target-env', 'vulkan1.0',
                    '-o', str(binary), str(port / f'vulkan_hud.{stage}')], check=True)
    subprocess.run(['spirv-val', '--target-env', 'vulkan1.0', str(binary)], check=True)
    data = binary.read_bytes()
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    shader_header += f'inline constexpr uint32_t EDEN_HUD_{stage.upper()}_SPV[] = {{\n'
    shader_header += ','.join(hex(word) for word in words) + '\n};\n'
path = output / 'vulkan_hud_shaders.h'
if not path.exists() or path.read_text() != shader_header:
    path.write_text(shader_header)
adapt('src/video_core/vulkan_common/vulkan.h', 'include/video_core/vulkan_common/vulkan.h',
      [('#else\n#define VK_USE_PLATFORM_XLIB_KHR', '#elif defined(PS5_NATIVE)\n// Native display-plane presentation, no desktop window-system headers.\n#else\n#define VK_USE_PLATFORM_XLIB_KHR')])
adapt('src/video_core/vulkan_common/vulkan_instance.cpp', 'vulkan_instance.cpp', [
    ('namespace Vulkan {', 'extern "C" VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetInstanceProcAddr(VkInstance, const char*);\n\nnamespace Vulkan {'),
    ('    case Core::Frontend::WindowSystemType::Headless:', '    case Core::Frontend::WindowSystemType::PS5:\n        extensions.push_back(VK_KHR_DISPLAY_EXTENSION_NAME);\n        break;\n    case Core::Frontend::WindowSystemType::Headless:'),
    ('#else\n    case Core::Frontend::WindowSystemType::X11:', '#elif !defined(PS5_NATIVE)\n    case Core::Frontend::WindowSystemType::X11:'),
    ('''    if (!library.IsOpen()) {
        LOG_ERROR(Render_Vulkan, "Vulkan library not available");
        throw vk::Exception(VK_ERROR_INITIALIZATION_FAILED);
    }
    if (!library.GetSymbol("vkGetInstanceProcAddr", &dld.vkGetInstanceProcAddr)) {
        LOG_ERROR(Render_Vulkan, "vkGetInstanceProcAddr not present in Vulkan");
        throw vk::Exception(VK_ERROR_INITIALIZATION_FAILED);
    }''', '    (void)library;\n    dld.vkGetInstanceProcAddr = &::vkGetInstanceProcAddr;'),
])
adapt('src/video_core/vulkan_common/vulkan_library.cpp', 'vulkan_library.cpp', [
    ('#if defined(__ANDROID__) && defined(ARCHITECTURE_arm64)', '#if defined(PS5_NATIVE)\n    return std::make_shared<Common::DynamicLibrary>();\n#elif defined(__ANDROID__) && defined(ARCHITECTURE_arm64)'),
])
adapt('src/video_core/vulkan_common/vulkan_wrapper.h', 'include/video_core/vulkan_common/vulkan_wrapper.h', [
    ('#include <array>', '#include <array>\n#include <cstdio>\n#include "performance.h"'),
    ('return dld->vkQueueSubmit(queue,', 'auto timer = Eden::Performance::VulkanTimer(2);\n        return dld->vkQueueSubmit(queue,'),
    ('return dld->vkQueueSubmit2(queue,', 'auto timer = Eden::Performance::VulkanTimer(2);\n        return dld->vkQueueSubmit2(queue,'),
    ('return dld->vkWaitForFences(owner,', 'auto timer = Eden::Performance::VulkanTimer(3);\n        return dld->vkWaitForFences(owner,'),
    ('const VkResult result = dld->vkWaitSemaphores(owner,', 'auto timer = Eden::Performance::VulkanTimer(4);\n        const VkResult result = dld->vkWaitSemaphores(owner,'),
    ('return dld->vkDeviceWaitIdle(handle);', 'auto timer = Eden::Performance::VulkanTimer(5);\n        return dld->vkDeviceWaitIdle(handle);'),
    ('''inline void Check(VkResult result) {
    if (result != VK_SUCCESS) {
        throw Exception(result);''', '''inline void Check(VkResult result, const char* file = __builtin_FILE(),
                  int line = __builtin_LINE(), const char* operation = __builtin_FUNCTION()) {
    if (result != VK_SUCCESS) {
        std::fprintf(stderr, "[EglantinePS5] Vulkan failure: %s:%d (%s) VkResult=%d\\n",
                     file, line, operation, static_cast<int>(result));
        throw Exception(result);'''),
])
adapt('src/video_core/vulkan_common/vulkan_wrapper.cpp', 'vulkan_wrapper.cpp', [
    ('#include "video_core/vulkan_common/vulkan_wrapper.h"', '#include "video_core/vulkan_common/vulkan_wrapper.h"\n#include "performance.h"'),
    ('auto const result = dld->vkCreateGraphicsPipelines(', 'auto timer = Eden::Performance::VulkanTimer(0);\n    auto const result = dld->vkCreateGraphicsPipelines('),
    ('Check(dld->vkCreateComputePipelines(', 'auto timer = Eden::Performance::VulkanTimer(1);\n    Check(dld->vkCreateComputePipelines('),
])
# The texture cache's collector and its downloads are Lichii's own: it collects by device memory
# block, takes a refused image as out of memory (RunGarbageCollector(out_of_memory)) and keeps old
# costly images apart. The port's collector for the Eglantine core (batched downloads, the console
# pool's pressure marks) is not carried over.
texture_costs = []
for signature, index in (
    ('RunGarbageCollector(bool out_of_memory)', 13), ('DownloadMemory(DAddr cpu_addr, size_t size)', 14),
    ('PopAsyncFlushes()', 15),
):
    anchor = f'void TextureCache<P>::{signature} {{'
    scope = f'''
    std::optional<Eden::Performance::Timer> cost_timer;
    if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {{
        if (Eden::Performance::vulkan_cost_enabled.load(std::memory_order_relaxed))
            cost_timer.emplace(Eden::Performance::vulkan_api[{index}]);
    }}
'''
    if index == 13:
        scope += '''    if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {
        if ((cost_timer || Eden::Performance::texture_budget_log.load(std::memory_order_relaxed)) &&
            frame_tick % 300 == 0)
            std::printf("EDEN_VULKAN_TEXTURE_BUDGET frame=%llu usage=%llu expected=%llu critical=%llu "
                        "keep_dirty=%d memory_short=%d\\n",
                        static_cast<unsigned long long>(frame_tick),
                        static_cast<unsigned long long>(total_used_memory),
                        static_cast<unsigned long long>(expected_memory),
                        static_cast<unsigned long long>(critical_memory),
                        int(Eden::Performance::gc_keep_dirty.load(std::memory_order_relaxed)),
                        int(Eden::Performance::graphics_memory_short.load(std::memory_order_relaxed)));
    }
'''
    texture_costs.append((anchor, anchor + scope))
VULKAN_CACHE = 'if constexpr (std::is_same_v<Runtime, Vulkan::TextureCacheRuntime>) {'
# Large textures re-upload only the block rows guest writes changed (headless/texture_partial.h).
# The Eglantine core has the mechanism (MarkPartialWrite / RefreshPartialContents) from 16 MiB on;
# ProsperoEden's takes images from 1 MiB on (dev-settings tex_partial_kb), which is what this sets.
# tex_partial=off keeps the core's bound; tex_partial_check=on compares each partial upload with a
# whole unswizzle.
texture_partial = [
    ('#include "video_core/texture_cache/texture_cache_base.h"',
     '#include "video_core/texture_cache/texture_cache_base.h"\n#include "texture_partial.h"\n#include "astc_policy.h"'),
    # The partial uploads from 1 MiB on (tex_partial) are not carried over: Lichii reworked the
    # mechanism (MarkPartialWrite / RefreshPartialContents) they changed.
]
# A large texture array (2D, several layers, 64 MiB or more) the CPU converts is uploaded a layer at
# a time, and an ASTC one converted in the background is decoded a layer at a time: Eden staged it
# whole, a heap buffer and a staging buffer each the image's size (341 and 361 MiB for Mario Kart
# World's terrain arrays) asked of the pool the guest's memory and the GPU share, at the moment a
# course loads - the requests that ended its sessions. The bytes are the same; the largest block is
# one layer. Arrays the GPU decodes keep the core's layer path (UploadsByLayer), and plain arrays its
# chunked one (UploadInChunks), so only converted ones take this (ProsperoEden: every CPU array).
LAYERED = ('image.info.type == ImageType::e2D && image.info.resources.layers > 1 && '
           'image.guest_size_bytes >= LayerUploadMinSize')
texture_layers = [
    ('    ++images_uploaded;\n'
     '    uploaded_bytes += image.guest_size_bytes;\n'
     '    largest_upload = (std::max<u64>)(largest_upload, image.guest_size_bytes);\n'
     '    if (!UploadInChunks(image)) {',
     '    ++images_uploaded;\n'
     '    uploaded_bytes += image.guest_size_bytes;\n'
     '    largest_upload = (std::max<u64>)(largest_upload, image.guest_size_bytes);\n'
     '    ' + VULKAN_CACHE + '\n'
     '        if (' + LAYERED + ' && True(image.flags & ImageFlagBits::Converted) &&\n'
     '            False(image.flags & (ImageFlagBits::AcceleratedUpload | ImageFlagBits::Sparse |\n'
     '                                 ImageFlagBits::Remapped | ImageFlagBits::Unbacked |\n'
     '                                 ImageFlagBits::TrimmedLevels))) {\n'
     '            const s32 layers = image.info.resources.layers;\n'
     '            ImageInfo layer_info = image.info;\n'
     '            layer_info.resources.layers = 1;\n'
     '            const size_t layer_map = MapSizeBytes(image) / layers;\n'
     '            for (s32 layer = 0; layer < layers; ++layer) {\n'
     '                const GPUVAddr layer_addr = image.gpu_addr + u64(layer) * image.info.layer_stride;\n'
     '                Tegra::Memory::GpuGuestMemory<u8, Tegra::Memory::GuestMemoryFlags::UnsafeRead> swizzle_data(\n'
     '                    *gpu_memory, layer_addr, image.info.layer_stride, &swizzle_data_buffer);\n'
     '                unswizzle_data_buffer.resize_destructive((std::max<size_t>)(\n'
     '                    image.unswizzled_size_bytes / layers, CalculateUnswizzledSizeBytes(layer_info)));\n'
     '                auto copies = UnswizzleImage(*gpu_memory, layer_addr, layer_info, swizzle_data,\n'
     '                                             unswizzle_data_buffer);\n'
     '                // The layer\'s converted size, where it is above the estimate (as the decode).\n'
     '                auto layout = copies;\n'
     '                ConvertedLayout(layer_info, layout);\n'
     '                const size_t layer_out = layout.empty() ? layer_map :\n'
     '                    (std::max<size_t>)(layer_map, layout.back().buffer_offset + layout.back().buffer_size);\n'
     '                auto layer_staging = runtime.UploadStagingBuffer(layer_out);\n'
     '                ConvertImage(unswizzle_data_buffer, layer_info, layer_staging.mapped_span, copies);\n'
     '                for (auto& copy : copies) copy.image_subresource.base_layer = layer;\n'
     '                image.UploadMemory(layer_staging, copies);\n'
     '            }\n'
     '            runtime.InsertUploadMemoryBarrier();\n'
     '            return;\n'
     '        }\n'
     '    }\n'
     '    if (!UploadInChunks(image)) {'),
    ('    image.flags |= ImageFlagBits::IsDecoding;\n'
     '    ++async_decodes_queued;\n'
     '    auto decode = std::make_unique<AsyncDecodeContext>();',
     '    ' + VULKAN_CACHE + '\n'
     '        if (' + LAYERED + ') {\n'
     '            image.flags |= ImageFlagBits::IsDecoding;\n'
     '            const s32 layers = image.info.resources.layers;\n'
     '            ImageInfo layer_info = image.info;\n'
     '            layer_info.resources.layers = 1;\n'
     '            const size_t layer_out = MapSizeBytes(image) / layers;\n'
     '            // A layer\'s own sizes, not a share of the whole image\'s estimates: a decode that\n'
     '            // wrote past its buffer corrupted the heap (TextureDecoder "mutex lock failed").\n'
     '            const size_t layer_in = (std::max<size_t>)(image.unswizzled_size_bytes / layers,\n'
     '                                                       CalculateUnswizzledSizeBytes(layer_info));\n'
     '            const bool zero = False(image.flags & ImageFlagBits::ZeroFilled);\n'
     '            image.flags |= ImageFlagBits::ZeroFilled;\n'
     '            for (s32 layer = 0; layer < layers; ++layer) {\n'
     '                ++async_decodes_queued;\n'
     '                auto layer_decode = std::make_unique<AsyncDecodeContext>();\n'
     '                auto* layer_ptr = layer_decode.get();\n'
     '                layer_decode->image_id = image_id;\n'
     '                async_decodes.push_back(std::move(layer_decode));\n'
     '                const GPUVAddr layer_addr = image.gpu_addr + u64(layer) * image.info.layer_stride;\n'
     '                std::vector<u8> layer_input(layer_in, 0);\n'
     '                Tegra::Memory::GpuGuestMemory<u8, Tegra::Memory::GuestMemoryFlags::UnsafeRead> layer_swizzle(\n'
     '                    *gpu_memory, layer_addr, image.info.layer_stride, &swizzle_data_buffer);\n'
     '                auto layer_copies = UnswizzleImage(*gpu_memory, layer_addr, layer_info, layer_swizzle,\n'
     '                                                   layer_input);\n'
     '                auto zero_copies = layer_copies;\n'
     '                ConvertedLayout(layer_info, zero_copies);\n'
     '                const size_t out = zero_copies.empty() ? layer_out :\n'
     '                    (std::max<size_t>)(layer_out, zero_copies.back().buffer_offset + zero_copies.back().buffer_size);\n'
     '                if (out > layer_out) {\n'
     '                    static std::atomic<u32> reported{};\n'
     '                    if (reported.fetch_add(1) < 8) {\n'
     '                        LOG_WARNING(HW_GPU, "Layer decode at {:#x} needs {} bytes, {} estimated", layer_addr, out, layer_out);\n'
     '                    }\n'
     '                }\n'
     '                if (zero) {\n'
     '                    for (auto& copy : zero_copies) copy.image_subresource.base_layer = layer;\n'
     '                    auto zero_staging = runtime.UploadStagingBuffer(out);\n'
     '                    std::memset(zero_staging.mapped_span.data(), 0, out);\n'
     '                    image.UploadMemory(zero_staging, zero_copies);\n'
     '                }\n'
     '                auto layer_func = [layer_out = out, layer, copies = layer_copies, info = layer_info,\n'
     '                                   input = std::move(layer_input), async_decode = layer_ptr]() mutable {\n'
     '                    async_decode->decoded_data.resize_destructive(layer_out);\n'
     '                    std::span copies_span{copies.data(), copies.size()};\n'
     '                    ConvertImage(input, info, async_decode->decoded_data, copies_span);\n'
     '                    for (auto& copy : copies) copy.image_subresource.base_layer = layer;\n'
     '                    async_decode->copies = std::move(copies);\n'
     '                    async_decode->complete.store(true, std::memory_order_release);\n'
     '                };\n'
     '                texture_decode_worker.QueueWork(std::move(layer_func));\n'
     '            }\n'
     '            if (zero) runtime.InsertUploadMemoryBarrier();\n'
     '            return;\n'
     '        }\n'
     '    }\n'
     '    image.flags |= ImageFlagBits::IsDecoding;\n'
     '    ++async_decodes_queued;\n'
     '    auto decode = std::make_unique<AsyncDecodeContext>();'),
    # A layer's result is staged at its own size, and the image stays decoding until its last
    # layer has landed (the collector does not take an image that is decoding).
    ('        auto staging = runtime.UploadStagingBuffer(MapSizeBytes(image));\n'
     '        std::memcpy(staging.mapped_span.data(), async_decode->decoded_data.data(),',
     '        auto staging = runtime.UploadStagingBuffer(async_decode->decoded_data.size());\n'
     '        std::memcpy(staging.mapped_span.data(), async_decode->decoded_data.data(),'),
    ('        image.UploadMemory(staging, async_decode->copies);\n'
     '        image.flags &= ~ImageFlagBits::IsDecoding;',
     '        image.UploadMemory(staging, async_decode->copies);\n'
     '        if (std::none_of(async_decodes.begin(), async_decodes.end(), [&](const auto& other) {\n'
     '                return other.get() != async_decode && other->image_id == async_decode->image_id &&\n'
     '                       !other->cancelled;\n'
     '            }))\n'
     '            image.flags &= ~ImageFlagBits::IsDecoding;'),
    # A whole-image decode too: its buffer at the converted layout's size where that is above
    # the estimate (TickAsyncDecode then drops the result with an error instead of the decode
    # writing past the buffer).
    ('    const size_t out_size = MapSizeBytes(image);\n',
     '    auto converted_layout = copies;\n'
     '    ConvertedLayout(image.info, converted_layout);\n'
     '    const size_t out_size = converted_layout.empty() ? MapSizeBytes(image) :\n'
     '        (std::max<size_t>)(MapSizeBytes(image), converted_layout.back().buffer_offset +\n'
     '                                                converted_layout.back().buffer_size);\n'),
]
# The decode thread hands a result over with complete's release store, the GPU thread takes it with
# an acquire load: no mutex per decode. Each one's std::mutex was created at its first lock, a
# texture array's course load queues one per layer (121 for a terrain array), and in 4 of ~24 races
# a decode thread's lock failed ("mutex lock failed: Invalid argument", 325-328 s into a session).
texture_decode_handoff = [
    ('        // TODO: Do we need this lock?\n'
     '        std::unique_lock lock{async_decode->mutex};\n'
     '        async_decode->copies = std::move(copies);\n'
     '        async_decode->complete = true;\n',
     '        async_decode->copies = std::move(copies);\n'
     '        async_decode->complete.store(true, std::memory_order_release);\n'),
    ('        {\n'
     '            // Release the lock before the context is erased below: unlocking it afterwards wrote\n'
     '            // into freed memory (heap corruption, crashes minutes into title 1).\n'
     '            std::unique_lock lock{async_decode->mutex};\n'
     '            if (!async_decode->complete) {\n'
     '                ++i;\n'
     '                continue;\n'
     '            }\n'
     '        }\n',
     '        // After this the context is the GPU thread\'s alone: the decode thread\'s store was\n'
     '        // its last touch of it.\n'
     '        if (!async_decode->complete.load(std::memory_order_acquire)) {\n'
     '            ++i;\n'
     '            continue;\n'
     '        }\n'),
]
# An ASTC texture kept as BC3 and converted on the CPU (accelerate_astc=CpuAsynchronous) is converted
# in the background in a busy frame only, and in place on a light screen (headless/astc_policy.h).
# The frame is counted where the texture cache ends its own; draws in RasterizerVulkan::PrepareDraw.
texture_astc_policy = [
    ('    if (True(image.flags & ImageFlagBits::AsynchronousDecode)) {\n        QueueAsyncDecode(image, image_id);\n        return;\n    }',
     '    if (True(image.flags & ImageFlagBits::AsynchronousDecode) && ::Eden::AstcPolicy::InBackground()) {\n        QueueAsyncDecode(image, image_id);\n        return;\n    }'),
    ('    TickAsyncDecode();\n    TickAsyncUnswizzle();', '    ::Eden::AstcPolicy::Frame();\n    TickAsyncDecode();\n    TickAsyncUnswizzle();'),
]
adapt('src/video_core/texture_cache/texture_cache.h',
      'vulkan-cache/video_core/texture_cache/texture_cache.h', [
    ('namespace VideoCommon {', '#include "performance.h"\n#include "common/scope_exit.h"\nnamespace Vulkan { class TextureCacheRuntime; }\n\nnamespace VideoCommon {'),
    # RADV reports all Vulkan allocations, not just cached textures. A game's
    # measured ~1.9 GiB working set triggered dirty eviction at the old 1.6 GiB
    # threshold despite a 4 GiB budget. Retain 40% headroom; keep the original
    # critical threshold and minimum 1 GiB spacing. OpenGL remains unchanged.
    ('const s64 min_vacancy_expected = (6 * mem_threshold) / 10;',
     'const s64 min_vacancy_expected =\n            ((std::is_same_v<Runtime, Vulkan::TextureCacheRuntime> ? 4 : 6) * mem_threshold) / 10;'),
] + texture_costs + texture_partial + texture_layers + texture_decode_handoff + texture_astc_policy)

# The four calls inside bind_geometry and the three inside bind_update. They sit in buffer_cache.h
# rather than in Configure, and both spend their time in SynchronizeBuffer's page walk over the
# memory tracker - once for the index buffer, once per enabled vertex buffer, once per per-stage
# segment, every draw, dirty or not. Which of the seven that is cannot be decided by reading it:
# the texture-buffer loop looked like the cost of bind and measured 2.8%.
adapt('src/video_core/buffer_cache/buffer_cache.h',
      'vulkan-cache/video_core/buffer_cache/buffer_cache.h', [
    ('        if (buffer_bytes >= 512_MiB) {\n'
     '            RunGarbageCollector(buffer_bytes >= 1_GiB);\n'
     '        }\n',
     '        const auto pressure = ::Eden::Performance::graphics_memory_probe.load(std::memory_order_relaxed);\n'
     '        const bool memory_short = frame_tick >= 60 && pressure && pressure();\n'
     '        if (buffer_bytes >= 512_MiB || memory_short) {\n'
     '            RunGarbageCollector(memory_short || buffer_bytes >= 1_GiB);\n'
     '        }\n'),
    ('++frames % 600 == 0', '++frames % 60 == 0'),
    ('#include "video_core/buffer_cache/buffer_cache_base.h"',
     '#include "video_core/buffer_cache/buffer_cache_base.h"\n#include "performance.h"'),
    ('void BufferCache<P>::BindHostGeometryBuffers(bool is_indexed) {',
     'void BufferCache<P>::BindHostGeometryBuffers(bool is_indexed) {\n'
     '    long long since_geo = ::Eden::Performance::MarkStart();'),
    ('    BindHostVertexBuffers();\n'
     '    BindHostTransformFeedbackBuffers();\n'
     '    if (current_draw_indirect) {\n'
     '        BindHostDrawIndirectBuffers();\n'
     '    }\n'
     '}',
     '    ::Eden::Performance::Mark(::Eden::Performance::geo_index, since_geo);\n'
     '    BindHostVertexBuffers();\n'
     '    ::Eden::Performance::Mark(::Eden::Performance::geo_vertex, since_geo);\n'
     '    BindHostTransformFeedbackBuffers();\n'
     '    ::Eden::Performance::Mark(::Eden::Performance::geo_xf, since_geo);\n'
     '    if (current_draw_indirect) {\n'
     '        BindHostDrawIndirectBuffers();\n'
     '    }\n'
     '    ::Eden::Performance::Mark(::Eden::Performance::geo_indirect, since_geo);\n'
     '}'),
    ('void BufferCache<P>::DoUpdateGraphicsBuffers(bool is_indexed) {',
     'void BufferCache<P>::DoUpdateGraphicsBuffers(bool is_indexed) {\n'
     '    long long since_upd = ::Eden::Performance::MarkStart();'),
    ('        UpdateTransformFeedbackBuffers();\n'
     '        for (size_t stage = 0; stage < NUM_STAGES; ++stage) {\n'
     '            UpdateUniformBuffers(stage);\n'
     '            UpdateStorageBuffers(stage);\n'
     '            UpdateTextureBuffers(stage);\n'
     '        }\n'
     '        if (current_draw_indirect) {\n'
     '            UpdateDrawIndirect();\n'
     '        }',
     '        UpdateTransformFeedbackBuffers();\n'
     '        ::Eden::Performance::Mark(::Eden::Performance::upd_state, since_upd);\n'
     '        for (size_t stage = 0; stage < NUM_STAGES; ++stage) {\n'
     '            UpdateUniformBuffers(stage);\n'
     '            UpdateStorageBuffers(stage);\n'
     '            UpdateTextureBuffers(stage);\n'
     '        }\n'
     '        ::Eden::Performance::Mark(::Eden::Performance::upd_stage, since_upd);\n'
     '        if (current_draw_indirect) {\n'
     '            UpdateDrawIndirect();\n'
     '        }\n'
     '        ::Eden::Performance::Mark(::Eden::Performance::upd_indirect, since_upd);'),
])

# These costs sit outside vkCreateGraphicsPipelines: guest shader translation,
# worker readiness, and background serialization can block different threads.
# The six phases inside Configure. draw_config is all of Configure but SetEngine's two pointer
# assignments, and ConfigureImpl is ~210 lines; without these the 2.78 us a draw spends
# configuring arrives as one number with nothing to aim at. One running clock, marked at the
# boundaries the source already has.
# Not carried over: Lichii's Configure has a full and a delta path (ConfigureImpl twice over).
configure_phases = []
for name in ('vk_graphics_pipeline', 'vk_compute_pipeline'):
    anchors = [
        ('#include <algorithm>', '#include <algorithm>\n#include "performance.h"'),
    ]
    if name == 'vk_graphics_pipeline':
        anchors += configure_phases
    adapt(f'src/video_core/renderer_vulkan/{name}.cpp', name + '_cost.cpp', anchors)
shader_costs = [
    ('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include <unordered_set>\n'
     '#include "performance.h"\n#include "dev_vulkan.h"\n#include "diagnostics.h"'),
    # Static vertex input (no attribute) for pipelines whose vertex shader reads no vertex attribute
    # (dev_vulkan.h static_vertex_input): with VK_EXT_vertex_input_dynamic_state the console's
    # driver drew them wrong (a full-screen triangle from the vertex index covering a game's
    # cutscenes with a flat colour). Building a pipeline records whether its vertex shader reads
    # attributes; the static key has no attribute, so the disk cache keeps loading it.
    ('#include "video_core/engines/maxwell_3d.h"',
     '#include "video_core/engines/maxwell_3d.h"\n#include "video_core/dirty_flags.h"\n'
     '#include <atomic>\n#include <mutex>\n#include <set>\n#include <unordered_set>\n'
     '#include "video_core/renderer_vulkan/vk_state_tracker.h"'),
    ('GraphicsPipeline* PipelineCache::CurrentGraphicsPipeline() {',
     """namespace {
std::mutex eden_attributeless_mutex;
using EdenVertexIdentity = std::array<u64, 2>;
std::set<EdenVertexIdentity> eden_attributeless_vertex;
std::atomic<u32> eden_attributeless_generation{0};
bool eden_static_vertex_input_bound = false;

void EdenRecordAttributeless(EdenVertexIdentity vertex_hash, const Shader::Info& info) {
    for (size_t index = 0; index < Shader::IR::NUM_GENERICS; ++index) {
        if (info.loads.Generic(index)) {
            return;
        }
    }
    std::scoped_lock lock{eden_attributeless_mutex};
    if (eden_attributeless_vertex.insert(vertex_hash).second) {
        eden_attributeless_generation.fetch_add(1, std::memory_order_release);
    }
}

// GPU thread: whether the vertex shader reads no attribute, as far as built pipelines tell.
bool EdenAttributeless(EdenVertexIdentity vertex_hash) {
    static EdenVertexIdentity last_hash{};
    static u32 last_generation = ~0u;
    static bool last_result = false;
    const u32 generation = eden_attributeless_generation.load(std::memory_order_acquire);
    if (vertex_hash != last_hash || generation != last_generation) {
        std::scoped_lock lock{eden_attributeless_mutex};
        last_hash = vertex_hash;
        last_generation = generation;
        last_result = eden_attributeless_vertex.contains(vertex_hash);
    }
    return last_result;
}

// A static key without attributes (what the loader takes back from the disk cache).
bool EdenAttributelessStaticKey(const FixedPipelineState& state) {
    return state.dynamic_vertex_input == 0 &&
           std::ranges::none_of(state.attributes,
                                [](const auto& attribute) { return attribute.raw != 0; });
}
} // Anonymous namespace

GraphicsPipeline* PipelineCache::CurrentGraphicsPipeline() {"""),
    ('    graphics_key.state.Refresh(*maxwell3d, dynamic_features);\n',
     """    graphics_key.state.Refresh(*maxwell3d, dynamic_features);
    const bool static_vertex_input = graphics_key.state.dynamic_vertex_input != 0 &&
                                     ::Eden::DevVulkan::static_vertex_input &&
                                     EdenAttributeless({graphics_key.unique_hashes[0], graphics_key.unique_hashes[1]});
    if (static_vertex_input) {
        // Instance-rate streams as the registers set them (with every stream per vertex the
        // driver drew these wrong too); no attribute, so the key does not depend on what the
        // registers hold for attributes the shader does not read.
        const auto& regs = maxwell3d->regs;
        graphics_key.state.dynamic_vertex_input.Assign(0);
        graphics_key.state.enabled_divisors = 0;
        graphics_key.state.attributes = {};
        graphics_key.state.binding_divisors = {};
        for (size_t index = 0; index < Maxwell::NumVertexArrays; ++index) {
            const bool is_enabled = regs.vertex_stream_instances.IsInstancingEnabled(index);
            graphics_key.state.binding_divisors[index] =
                is_enabled ? regs.vertex_streams[index].frequency : 0;
            graphics_key.state.enabled_divisors |= (is_enabled ? u64{1} : 0) << index;
        }
        // The union's attribute_types now holds divisors: the next dynamic draw recomputes them
        // and sets its vertex input again (a static pipeline replaced it).
        maxwell3d->dirty.flags[Dirty::VertexInput] = true;
    }
    if (static_vertex_input && !eden_static_vertex_input_bound) {
        // Rebind the vertex buffers with their strides, dynamic state of the static pipeline.
        auto& flags = maxwell3d->dirty.flags;
        flags[VideoCommon::Dirty::VertexBuffers] = true;
        for (size_t index = 0; index < Maxwell::NumVertexArrays; ++index) {
            flags[VideoCommon::Dirty::VertexBuffer0 + index] = true;
        }
    }
    eden_static_vertex_input_bound = static_vertex_input;
"""),
    ('        (key.state.dynamic_vertex_input != 0) != dynamic_features.has_dynamic_vertex_input) {',
     '        ((key.state.dynamic_vertex_input != 0) != dynamic_features.has_dynamic_vertex_input &&\n'
     '         !(dynamic_features.has_dynamic_vertex_input &&\n'
     '           ::Eden::DevVulkan::static_vertex_input &&\n'
     '           EdenAttributelessStaticKey(key.state)))) {'),
    # Where a pipeline is made from translated programs (a rebuild from kept stages was recorded
    # when those were first made).
    ('    const bool defer_emission = ir_reservation != nullptr;\n'
     '    std::array<const Shader::Info*, Maxwell::MaxShaderStage> infos{};\n',
     '    const bool defer_emission = ir_reservation != nullptr;\n'
     '    if (uses_vertex_b) {\n'
     '        EdenRecordAttributeless({key.unique_hashes[0], key.unique_hashes[1]}, programs[1].info);\n'
     '    }\n'
     '    std::array<const Shader::Info*, Maxwell::MaxShaderStage> infos{};\n'),
]
# The translation timers, the first-use trace and the driver cache's write-then-rename are not
# carried over: Lichii's pipeline cache defers emission, rebuilds from kept stages and already
# writes vulkan_pipelines.bin beside the old file.
shader_source = (source / 'src/video_core/renderer_vulkan/vk_pipeline_cache.cpp').read_text()
for old, new in shader_costs:
    if shader_source.count(old) != 1:
        if report:
            broken.append(f"src/video_core/renderer_vulkan/vk_pipeline_cache.cpp: {old[:70]!r} (matches {shader_source.count(old)})")
            continue
        raise RuntimeError(f'Shader pipeline anchor changed: {old[:60]}')
    shader_source = shader_source.replace(old, new)
shader_output = output / 'vk_pipeline_cache_cost.cpp'
if not shader_output.exists() or shader_output.read_text() != shader_source:
    shader_output.write_text(shader_source)

# Scope only the existing synchronous operations; never alter their ordering.
# Report these caller costs separately from the overlapping API totals.
import re
# Development GPU fault probes (dev_vulkan.h): multi-range storage buffers are
# the one path that binds sparse ranges of the console's device memory.
probes = {
    'vk_multi_range_buffer': [
        ('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include "dev_vulkan.h"\n#include "diagnostics.h"'),
        ('    if (bind_result != VK_SUCCESS) {\n        return SparseBuffer{};\n    }',
         '    if (bind_result != VK_SUCCESS) {\n'
         '        if (::Eden::DevVulkan::trace_pipelines) ::Eden::Report("multirange", "sparse bind failed");\n'
         '        return SparseBuffer{};\n    }'),
        ('    retired.push_back(Retired{',
         '    if (::Eden::DevVulkan::trace_pipelines) {\n'
         '        static unsigned retires = 0;\n'
         '        if (++retires <= 64) {\n'
         '            char text[96];\n'
         '            std::snprintf(text, sizeof(text), "retire #%u sparse=%d tick=%llu", retires,\n'
         '                          int(bool(entry.sparse_handle)), (unsigned long long)scheduler.CurrentTick());\n'
         '            ::Eden::Report("multirange", text);\n'
         '        }\n'
         '    }\n'
         '    retired.push_back(Retired{'),
        ('    entries.emplace(key, std::move(entry));',
         '    if (::Eden::DevVulkan::trace_pipelines) {\n'
         '        static unsigned created = 0;\n'
         '        if (++created <= 256) {\n'
         '            char text[192];\n'
         '            std::snprintf(text, sizeof(text), "new #%u key=%llx total=%llu sources=%zu sparse=%d addr=%llx",\n'
         '                          created, (unsigned long long)key, (unsigned long long)total, sources.size(),\n'
         '                          int(bool(entry.sparse_handle)), (unsigned long long)entry.address);\n'
         '            ::Eden::Report("multirange", text);\n'
         '        }\n'
         '    }\n'
         '    entries.emplace(key, std::move(entry));'),
    ],
    'vk_buffer_cache': [
        ('#include <algorithm>', '#include <algorithm>\n#include "dev_vulkan.h"\n#include "submission_origin.h"'),
        ('void BufferCacheRuntime::Finish() {',
         'void BufferCacheRuntime::Finish() {\n'
         '    ::Eden::VulkanProbe::GpuSubmitOriginScope origin{__builtin_return_address(0), true};'),
        ('bool BufferCacheRuntime::BindMultiRangeStorageBuffer(u64 key, bool is_written) {\n',
         'bool BufferCacheRuntime::BindMultiRangeStorageBuffer(u64 key, bool is_written) {\n'
         '    if (::Eden::DevVulkan::disable_multi_range) {\n        return false;\n    }\n'),
    ],
    # With custom border colours off (the console default), report which clamp-to-border
    # samplers ask for a colour the three standard ones cannot give exactly.
    'vk_texture_cache': [
        ('void TextureCacheRuntime::Finish() {',
         'void TextureCacheRuntime::Finish() {\n'
         '    ::Eden::VulkanProbe::GpuSubmitOriginScope origin{__builtin_return_address(0), true};'),
        ('void TextureCacheRuntime::TranscodeAstcToBcn(\n'
         '    Image& image, const StagingBufferRef& map,\n'
         '    std::span<const VideoCommon::SwizzleParameters> swizzles) {\n',
         'void TextureCacheRuntime::TranscodeAstcToBcn(\n'
         '    Image& image, const StagingBufferRef& map,\n'
         '    std::span<const VideoCommon::SwizzleParameters> swizzles) {\n'
         '    ::Eden::Performance::Timer mkw_timer(::Eden::Performance::mkw_transcode);\n'),
        # An ASTC-to-BC transcode decodes into an RGBA copy (4 bytes a pixel, every level) that
        # lives until the GPU has used it. A course load makes hundreds in a frame, which held
        # 6.7 GB of the pool the console's GPU shares with the CPU (ProsperoEden). So the copies in
        # flight are bounded by bytes (256 MiB, or EDEN_PS5_TRANSCODE_PENDING_MIB), waiting for the
        # oldest copy only; what is recorded is submitted every 32 MiB, so the GPU works through
        # the copies while more are recorded. Lichii keeps finished decode images for reuse
        # (free_transcodes, bounded on its own); this bounds the ones the GPU still has.
        ('    PendingTranscode pending;\n    if (reusable != free_transcodes.end()) {',
         '    {\n'
         '        using namespace Common::Literals;\n'
         '        static const u64 held_limit = [] {\n'
         '            const char* value = std::getenv("EDEN_PS5_TRANSCODE_PENDING_MIB");\n'
         '            return value != nullptr ? std::strtoull(value, nullptr, 10) << 20 : u64{256_MiB};\n'
         '        }();\n'
         '        // RGBA8 with a full mip chain: a third more than the base level.\n'
         '        const auto copy_bytes = [](u64 w, u64 h, u64 l) { return w * h * 4 * l * 4 / 3; };\n'
         '        const u64 decode_bytes = copy_bytes(width, height, layers);\n'
         '        u64 held_bytes = 0, recorded_bytes = 0;\n'
         '        for (const PendingTranscode& held : pending_transcodes) {\n'
         '            const u64 bytes = copy_bytes(held.width, held.height, held.layers);\n'
         '            held_bytes += bytes;\n'
         '            recorded_bytes += held.tick >= scheduler.CurrentTick() ? bytes : 0;\n'
         '        }\n'
         '        if (recorded_bytes >= 32_MiB) {\n'
         '            scheduler.Flush();\n'
         '        }\n'
         '        while (!pending_transcodes.empty() && held_bytes + decode_bytes > held_limit) {\n'
         '            scheduler.Wait(pending_transcodes.front().tick);\n'
         '            while (!pending_transcodes.empty() && scheduler.IsFree(pending_transcodes.front().tick)) {\n'
         '                const PendingTranscode& done = pending_transcodes.front();\n'
         '                held_bytes -= copy_bytes(done.width, done.height, done.layers);\n'
         '                pending_transcodes.pop_front();\n'
         '            }\n'
         '        }\n'
         '    }\n'
         '    PendingTranscode pending;\n    if (reusable != free_transcodes.end()) {'),
        ('#include <algorithm>', '#include <algorithm>\n#include <cstdio>\n#include "dev_vulkan.h"\n#include "diagnostics.h"\n#include "submission_origin.h"'),
        ('    has_custom_border_colors = samples_border && device.IsCustomBorderColorUsable();',
         '    if (::Eden::DevVulkan::trace_pipelines && samples_border) {\n'
         '        static std::vector<std::array<float, 4>> reported;\n'
         '        const auto report = [](const std::array<float, 4>& c, const char* kind) {\n'
         '            if (c == std::array<float, 4>{0, 0, 0, 0} || c == std::array<float, 4>{0, 0, 0, 1} ||\n'
         '                c == std::array<float, 4>{1, 1, 1, 1} || reported.size() >= 32 ||\n'
         '                std::find(reported.begin(), reported.end(), c) != reported.end()) return;\n'
         '            reported.push_back(c);\n'
         '            char text[128];\n'
         '            std::snprintf(text, sizeof(text), "non-standard %s border %g %g %g %g", kind, c[0], c[1],\n'
         '                          c[2], c[3]);\n'
         '            ::Eden::Report("sampler", text);\n'
         '        };\n'
         '        report(border_color, "linear");\n'
         '        if (tsc.srgb_conversion) report(srgb_border_color, "srgb");\n'
         '    }\n'
         '    has_custom_border_colors = samples_border && device.IsCustomBorderColorUsable();'),
    ],
}
for name, index, expected in (
    ('vk_fence_manager', 6, 1), ('vk_buffer_cache', 7, 6),  # three diagnostic mapped-readback probe waits
    ('vk_texture_cache', 8, 1), ('vk_swapchain', 9, 6),
    ('vk_descriptor_buffer', 10, 2), ('vk_multi_range_buffer', 11, 1),
    ('vk_compute_pass', 12, 1),
):
    relative = f'src/video_core/renderer_vulkan/{name}.cpp'
    destination = 'vulkan_swapchain.cpp' if name == 'vk_swapchain' else name + '_cost.cpp'
    # Preserve the earlier swapchain error-recovery adaptation.
    path = output / destination
    text = path.read_text() if name == 'vk_swapchain' else (source / relative).read_text()
    pattern = r'(?m)^( +)(scheduler\.(?:Wait|Finish)\([^\n]*\);)$'
    matches = list(re.finditer(pattern, text))
    # The counts are the Eglantine core's; Lichii's differ (five in vk_buffer_cache), and every
    # wait found is timed whatever their number.
    if len(matches) != expected:
        print(f'Wait sites in {name}: {len(matches)} (the Eglantine core had {expected})', file=sys.stderr)
    text = re.sub(pattern, lambda m: m[1] + '{ auto timer = Eden::Performance::VulkanTimer('
                  + str(index) + '); ' + m[2] + ' }', text)
    if name == 'vk_compute_pass':
        # ASTC decode has no CPU consumer. Its existing image barrier orders
        # later shaders, and staging/descriptor reuse is protected by ticks.
        text = text.replace('VulkanTimer(12); scheduler.Finish();',
                            'VulkanTimer(12); scheduler.Flush();')
    for probe_old, probe_new in probes.get(name, []):
        if text.count(probe_old) != 1:
            if report:
                broken.append(f"{relative}: {probe_old[:70]!r} (matches {text.count(probe_old)})")
                continue
            raise RuntimeError(f'Probe anchor changed: {name}: {probe_old[:60]}')
        text = text.replace(probe_old, probe_new)
    text = '#include "performance.h"\n' + text
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
# Eden loads these shaders when the renderer starts, whether frames are to be generated or not:
# the reasons are only written when the setting is on, or every session without the user's
# Lossless.dll would say so.
adapt('src/video_core/renderer_vulkan/present/lsfg_shaders.cpp', 'vulkan_lsfg_shaders.cpp', [
    ('#include "video_core/vulkan_common/vulkan_device.h"',
     '#include <string>\n#include "common/settings.h"\n#include "video_core/vulkan_common/vulkan_device.h"\n#include "diagnostics.h"'),
    ("""    valid = true;""",
     """    valid = true;
    if (wanted)
        Eden::Report("framegen", ("shaders ready: " + std::to_string(code.size()) + " modules").c_str());"""),
])
# Two members, so that "frames are being generated" and "this image cannot take them" are said once
# per session rather than once per process or once per frame: this object is built per renderer,
# and the renderer is built per game session.
adapt('src/video_core/renderer_vulkan/present/frame_gen.h',
      'include/video_core/renderer_vulkan/present/frame_gen.h', [
    ('    bool dumped{};', '    bool dumped{};\n    bool generation_reported{};\n    bool storage_reported{};'),
])
adapt('src/video_core/renderer_vulkan/present/frame_gen.cpp', 'vulkan_frame_gen.cpp', [
    ('#include "video_core/vulkan_common/vulkan_device.h"',
     '#include "video_core/vulkan_common/vulkan_device.h"\n#include "diagnostics.h"'),
    # The gates above only say why it is not running; this says that it is.
    ("""    generated = warm && warm_streak >= LSFG_RECURRENCE_FRAMES && plan.generations > 0;""",
     """    generated = warm && warm_streak >= LSFG_RECURRENCE_FRAMES && plan.generations > 0;
    if (generated && !generation_reported) {
        generation_reported = true;
        Eden::Report("framegen",
                     ("generating " + std::to_string(plan.generations) +
                      " extra frame(s) per guest frame").c_str());
    }"""),
])
# Split the dispatch into its three phases (Tegra::Control::Scheduler::Push): the channel lock,
# queueing the submit list, and executing the guest's methods. The dispatch timer wraps the whole
# call from gpu_thread.cpp, so these say which of the three it is spent in.
adapt('src/video_core/control/scheduler.cpp', 'control_scheduler.cpp', [
    ('#include <memory>', '#include <memory>\n#include "performance.h"'),
    ('        std::unique_lock lk(scheduling_guard);\n'
     '        auto it = channels.find(channel);\n'
     '        ASSERT(it != channels.end());\n'
     '        channel_state = it->second;\n'
     '    }\n'
     '    BindChannel(gpu, channel_state->bind_id);\n'
     '    // Process commands outside the lock to reduce contention.\n'
     '    // Multiple channels can prepare their commands in parallel.\n'
     '    channel_state->payload->dma_pusher.Push(std::move(entries));\n'
     '    channel_state->payload->dma_pusher.DispatchCalls();',
     '        const ::Eden::Performance::Timer sched_lock_timer(::Eden::Performance::gpu_sched_lock);\n'
     '        std::unique_lock lk(scheduling_guard);\n'
     '        auto it = channels.find(channel);\n'
     '        ASSERT(it != channels.end());\n'
     '        channel_state = it->second;\n'
     '    }\n'
     '    BindChannel(gpu, channel_state->bind_id);\n'
     '    // Process commands outside the lock to reduce contention.\n'
     '    // Multiple channels can prepare their commands in parallel.\n'
     '    {\n'
     '        const ::Eden::Performance::Timer dma_push_timer(::Eden::Performance::gpu_dma_push);\n'
     '        channel_state->payload->dma_pusher.Push(std::move(entries));\n'
     '    }\n'
     '    {\n'
     '        const ::Eden::Performance::Timer dma_dispatch_timer(::Eden::Performance::gpu_dma_dispatch);\n'
     '        channel_state->payload->dma_pusher.DispatchCalls();\n'
     '    }'),
])
shader_header = '#pragma once\n#include <cstdint>\n'
for stage in ('vert', 'frag'):
    binary = output / f'vulkan_hud.{stage}.spv'
    subprocess.run(['glslangValidator', '-V', '--target-env', 'vulkan1.0',
                    '-o', str(binary), str(port / f'vulkan_hud.{stage}')], check=True)
    subprocess.run(['spirv-val', '--target-env', 'vulkan1.0', str(binary)], check=True)
    data = binary.read_bytes()
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    shader_header += f'inline constexpr uint32_t EDEN_HUD_{stage.upper()}_SPV[] = {{\n'
    shader_header += ','.join(hex(word) for word in words) + '\n};\n'
path = output / 'vulkan_hud_shaders.h'
if not path.exists() or path.read_text() != shader_header:
    path.write_text(shader_header)
if broken:
    print(f"{len(broken)} anchor(s) of the Eden source changed; adapt them in tools/prepare-vulkan-port.py:", file=sys.stderr)
    for line in broken:
        print("  " + line, file=sys.stderr)
    sys.exit(1)

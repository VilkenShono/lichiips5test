// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise retained pipelines and colliding wait channels with out-of-order completion.
#include "striped_wait.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <memory>
#include <thread>
#include <unordered_set>
#include <vector>
struct Pipeline {
    Eden::StripedCondition condition;
    Eden::StripedMutex mutex;
    bool built = false;
};
int main() {
    constexpr unsigned count = 16000;
    auto pipelines = std::make_unique<Pipeline[]>(count);
    std::unordered_set<void*> locks, conditions;
    std::vector<unsigned> collision;
    const auto slot = Eden::StripedWait::SlotOf(&pipelines[0].condition);
    for (unsigned i = 0; i < count; ++i) {
        locks.insert(&Eden::StripedWait::MutexFor(&pipelines[i].mutex));
        conditions.insert(&Eden::StripedWait::ConditionFor(&pipelines[i].condition));
        std::lock_guard lock(pipelines[i].mutex);
        if (Eden::StripedWait::SlotOf(&pipelines[i].condition) == slot && collision.size() < 24)
            collision.push_back(i);
    }
    assert(locks.size() <= 64 && conditions.size() <= 64 && collision.size() == 24);
    std::atomic<unsigned> started{0}, finished{0};
    std::vector<std::thread> waiters;
    for (unsigned i : collision) {
        waiters.emplace_back([&, i] {
            std::unique_lock lock(pipelines[i].mutex);
            started.fetch_add(1);
            pipelines[i].condition.wait(lock, [&] { return pipelines[i].built; });
            assert(pipelines[i].built);
            finished.fetch_add(1);
        });
    }
    while (started.load() != collision.size()) std::this_thread::yield();
    // A broadcast with false predicates must not complete any pipeline.
    pipelines[0].condition.notify_all();
    assert(finished.load() == 0);
    for (auto it = collision.rbegin(); it != collision.rend(); ++it) {
        auto& pipeline = pipelines[*it];
        { std::lock_guard lock(pipeline.mutex); pipeline.built = true; }
        pipeline.condition.notify_one();
    }
    for (auto& waiter : waiters) waiter.join();
    assert(finished.load() == collision.size());
    // Immediate completion, and destruction/recreation at the same addresses.
    for (int cycle = 0; cycle < 3; ++cycle) {
        pipelines = std::make_unique<Pipeline[]>(count);
        for (unsigned i = 0; i < count; ++i) {
            std::unique_lock lock(pipelines[i].mutex);
            pipelines[i].built = true;
            pipelines[i].condition.wait(lock, [&] { return pipelines[i].built; });
        }
    }
    std::printf("PASS 16000 retained pipelines: %zu lock/%zu condition slots, colliding waiters and relaunch lifecycle\n",
                locks.size(), conditions.size());
}

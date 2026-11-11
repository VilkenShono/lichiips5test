// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cstdint>
#include <condition_variable>
#include <chrono>
#include <deque>
#include <map>
#include <span>
#include <utility>
#include <mutex>
#include <vector>
#include "ps5_pad.hpp"
namespace Eden::Mock {
struct State {
    std::mutex mutex;
    std::condition_variable wake;
    std::deque<ps5::pad::Data> pad_samples;
    int user_init_result = 0, user_result = 0, pad_open_result = 7, read_result = 0;
    int foreground_user = 84, last_pad_user = -1;
    int user_terminations = 0, pad_closes = 0, pad_opens = 0;
    std::vector<ps5::pad::Vibration> vibrations;
    bool fail_audio_open = false, fail_volume = false, fail_output = false;
    int audio_opens = 0, audio_closes = 0, audio_drains = 0;
    std::map<int, std::vector<std::array<std::int16_t, 512>>> audio;
    bool guest_input = false;
    std::chrono::steady_clock::time_point guest_start;
    // The pad's vibration audio port (type 10, pad_haptics.cpp): handles from 301, blocks kept as
    // bytes since the stream may be S16 or F32, the newest 256 per port.
    std::vector<std::pair<int, int>> vibration_modes;  // (pad handle, mode) per scePadSetVibrationMode
    int vibration_mode_1_result = 0;                   // what selecting advanced mode returns
    bool fail_haptic_open = false, fail_haptic_output = false;
    int haptic_fail_format = 0;                        // a format the vibration port refuses (0: none)
    int haptic_opens = 0, haptic_closes = 0, haptic_drains = 0;
    std::vector<int> haptic_open_users, haptic_open_formats;
    std::chrono::milliseconds haptic_close_delay{0};
    std::map<int, std::deque<std::vector<std::uint8_t>>> haptic_audio;
};
extern State state;
void BeginGuestCycle();
void CheckGuestCycle();
std::array<std::int16_t, 960> HighRendererReference();
bool RendererPcmMatches(std::span<const std::int16_t> pcm, bool high = false);
}

// Simulates the HMMA_NATIVE algorithm over 32 lanes (PTX m16n8k16 / m16n8k8 f16 fragment layouts)
// and checks D against a reference matrix product with the same f32 accumulation and f16 rounding.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>
using h16 = _Float16;
static uint32_t pack(h16 lo, h16 hi) { uint16_t a, b; std::memcpy(&a, &lo, 2); std::memcpy(&b, &hi, 2); return a | (uint32_t(b) << 16); }
static float half_of(uint32_t v, int h) { uint16_t x = h ? v >> 16 : v & 0xffff; h16 f; std::memcpy(&f, &x, 2); return float(f); }
static float rnd(float v) { return float(h16(v)); }
int main() {
    std::mt19937 rng(7); std::uniform_real_distribution<float> d(-2, 2);
    int bad = 0;
    for (int depth : {8, 16}) for (int iter = 0; iter < 200; ++iter) {
        float A[16][16], B[16][8], C[16][8];
        for (auto& r : A) for (auto& v : r) v = float(h16(d(rng)));
        for (auto& r : B) for (auto& v : r) v = float(h16(d(rng)));
        for (auto& r : C) for (auto& v : r) v = float(h16(d(rng)));
        uint32_t ra[32][4], rb[32][2], rc[32][2];
        for (int t = 0; t < 32; ++t) {
            int g = t / 4, q = t % 4;
            ra[t][0] = pack(h16(A[g][2*q]), h16(A[g][2*q+1]));     ra[t][1] = pack(h16(A[g+8][2*q]), h16(A[g+8][2*q+1]));
            ra[t][2] = pack(h16(A[g][2*q+8]), h16(A[g][2*q+9]));   ra[t][3] = pack(h16(A[g+8][2*q+8]), h16(A[g+8][2*q+9]));
            rb[t][0] = pack(h16(B[2*q][g]), h16(B[2*q+1][g]));     rb[t][1] = pack(h16(B[2*q+8][g]), h16(B[2*q+9][g]));
            rc[t][0] = pack(h16(C[g][2*q]), h16(C[g][2*q+1]));     rc[t][1] = pack(h16(C[g+8][2*q]), h16(C[g+8][2*q+1]));
        }
        for (int t = 0; t < 32; ++t) {
            // HMMA_NATIVE, lane t
            int chunks = depth == 16 ? 2 : 1;
            float acc[2][2];
            for (int r = 0; r < 2; ++r) for (int c = 0; c < 2; ++c) acc[r][c] = half_of(rc[t][r], c);
            for (int ch = 0; ch < chunks; ++ch) {
                for (int k = 0; k < 4; ++k) {
                    int al = (t & 0x1c) | k; uint32_t av[2] = {ra[al][ch*2], ra[al][ch*2+1]};
                    uint32_t bv[2]; for (int c = 0; c < 2; ++c) bv[c] = rb[((t & 3) << 3) + c*4 + k][ch];
                    for (int r = 0; r < 2; ++r) for (int h = 0; h < 2; ++h) { float a = half_of(av[r], h);
                        for (int c = 0; c < 2; ++c) acc[r][c] = std::fma(a, half_of(bv[c], h), acc[r][c]); }
                }
                for (auto& r : acc) for (auto& v : r) v = rnd(v);
            }
            // reference: same order (k ascending, f32 fma), rounding after each 8 k
            int g = t / 4, q = t % 4;
            for (int r = 0; r < 2; ++r) for (int c = 0; c < 2; ++c) {
                int row = g + 8*r, col = 2*q + c; float ref = C[row][col];
                for (int k = 0; k < depth; ++k) { ref = std::fma(A[row][k], B[k][col], ref); if (k % 8 == 7) ref = rnd(ref); }
                if (ref != acc[r][c]) { if (bad++ < 5) std::printf("mismatch depth=%d lane=%d r=%d c=%d %f %f\n", depth, t, r, c, ref, acc[r][c]); }
            }
        }
    }
    std::printf("%s (%d mismatches)\n", bad ? "FAIL" : "PASS", bad);
}

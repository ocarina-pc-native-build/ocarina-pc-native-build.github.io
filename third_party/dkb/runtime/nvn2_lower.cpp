// NVN 2 program stage -> the NVN 1 shape the rest of the host takes (gfx_shader.c, vk_exec_draw.c): Eglantine's
// lowering (runtime/third_party/eglantine, GPL-3.0-or-later) rewrites the Ampere code as Maxwell, laid out as TotK's
// translator reads it, and a synthetic control block carries the fields the host reads.
#include <cstdint>
#include <cstdlib>
#include <atomic>
#include <cstring>
#include <map>
#include <set>
#include <mutex>
#include <unordered_map>
#include <utility>
#include <vector>
#include "nvn2_control.h"
#include "nvn_mesh.h"

#include "shader_recompiler/frontend/ampere/program_capture.h"

// Lichii v13's lowering (third_party/lichii, GPL-3.0-or-later) under its own namespace: the fallback for programs the
// Eglantine lowering above rejects. It lowers, among others, the global reductions (RED) of Ocarina's vegetation
// culling and sky ambient compute programs, whose rejection blocked their GPU work and left leaves and grass at a count
// of zero.
#define Ampere AmpereLichii
#include "third_party/lichii/program_capture.h"
#undef Ampere

extern "C" void rt_log(const char *fmt, ...);
extern "C" uint64_t gfx_shader_nvn2_hash(const uint8_t *control, const uint8_t *code);

namespace {
constexpr size_t kControl = 0x880;   // gfx_shader.c CONTROL_SIZE
constexpr size_t kC0Layout = 0x860;  // "DKC1" + compute parameter layout (gfx_shader.c NVN2_C0_LAYOUT)
constexpr uint64_t kMaxwellNop = 0x50b0000000070f00ull;
constexpr uint64_t kMaxwellExit = 0xe30000000007000full;

struct Lowered { std::vector<uint8_t> control; std::vector<uint64_t> code; uint64_t origin; };
std::mutex lock;
// Keyed by content, not by address: a game frees program memory and loads other shaders at the same place (a scene
// change), and an address key handed those the old lowering. The key is gfx_shader_nvn2_hash (the dump name).
// ponytail: kept for the process (a few thousand small stages); free with the program if memory ever matters
std::map<uint64_t, Lowered *> cache;
std::atomic<uint64_t> failures{0}; // distinct rejected shader stages, not just downstream SPIR-V errors
std::set<std::pair<uint64_t,unsigned>> failed_program_uses;
std::set<uint64_t> active_failed_shaders;
// Lowered code buffer -> its key, for nvn2_origin: the draw path asks it on every draw (vk_exec_draw.c
// light_quad_fault_skip), and a scan of the cache there cost most of the render thread in heavy scenes.
std::unordered_map<const uint8_t *, uint64_t> origins;

void put32(std::vector<uint8_t> &c, size_t at, uint32_t v) { std::memcpy(c.data() + at, &v, 4); }

Lowered *lower(const uint8_t *control, const uint8_t *code) {
    uint32_t control_bytes;
    std::memcpy(&control_bytes, control + 0x30, sizeof control_bytes);
    if (!control_bytes) control_bytes = 0xd8;
    const unsigned native_stage = nvn2_control_stage(control, control_bytes);
    uint32_t code_len, w0;
    std::memcpy(&code_len, control + 0x38, 4), std::memcpy(&w0, code, 4);
    const bool task = native_stage == NVN2_STAGE_TASK;
    const bool mesh = task || native_stage == NVN2_STAGE_MESH;
    NvnMeshInfo mesh_info{};
    uint32_t stage_memory[4]{};
    if (mesh) {
        auto u16 = [&](unsigned at) { return uint32_t(control[at]) | uint32_t(control[at+1]) << 8; };
        mesh_info.magic = NVN_MESH_META_MAGIC;
        mesh_info.threads = u16(0x58); mesh_info.payload = u16(0x5a);
        mesh_info.vertices = u16(0x60); mesh_info.primitives = u16(0x62);
        mesh_info.uses_task = control[0x5e];
        if (mesh_info.threads != 32 || mesh_info.payload > 16384 || (!task && (mesh_info.vertices > 256 ||
            !mesh_info.vertices || !mesh_info.primitives || mesh_info.primitives > 255 || (control[0x68] & 0x80)))) {
            rt_log("nvn2: mesh %016llx unsupported task/workgroup/primitive metadata: %s, threads %u (32), payload %u "
                   "(<= 16384), vertices %u (1-256), primitives %u (1-255), control +0x68 %#x (bit 7 clear)",
                   (unsigned long long)gfx_shader_nvn2_hash(control, code), task ? "task" : "mesh", mesh_info.threads,
                   mesh_info.payload, mesh_info.vertices, mesh_info.primitives, control[0x68]);
            return nullptr;
        }
        for (unsigned k=0;!task && k<4;k++) if ((code[0x35] >> (k+4)) & 1)
            mesh_info.attribute[mesh_info.components++] = uint8_t(128+k);
        for (unsigned k=0;!task && k<128;k++) if ((code[0x36+k/8] >> (k%8)) & 1)
            mesh_info.attribute[mesh_info.components++] = uint8_t(k);
        if (!task && (code[0x35] & 0xf0) != 0xf0) return nullptr;
        mesh_info.output_base = 0x10 + ((mesh_info.payload+15)&~15u);
        unsigned blocks = (std::max(mesh_info.vertices,mesh_info.primitives)+31)/32;
        mesh_info.primitive_base = mesh_info.output_base + blocks*mesh_info.components*128;
        mesh_info.shared_bytes = (mesh_info.primitive_base + 4 + 3*mesh_info.primitives + 127)&~127u;
        if (task) mesh_info.shared_bytes = (mesh_info.output_base + mesh_info.payload + 127)&~127u;
        if (mesh_info.shared_bytes > 32768) return nullptr;
        stage_memory[0]=0; stage_memory[1]=0x10;
        stage_memory[2]=mesh_info.output_base; stage_memory[3]=mesh_info.primitive_base;
    }
    const bool gfx = nvn2_sph_type(w0) != 0;
    const uint32_t hdr = gfx ? 0x80 : 0;
    if (code_len <= hdr) {
        rt_log("nvn2: stage with %#x bytes of code (header %#x, word 0 %#x): nothing to lower", code_len, hdr, w0);
        return nullptr;
    }

    std::vector<Shader::Ampere::Instruction> native;
    Shader::Ampere::ProgramCaptureState capture;
    for (uint32_t at = hdr; at + 16 <= code_len; at += 16) {
        Shader::Ampere::Instruction insn;
        std::memcpy(insn.words.data(), code + at, 16);
        if (mesh) {
            unsigned op=insn.Bits(0,12);
            if (op==0x984 || op==0x388 || op==0x38c || op==0x988 || op==0x98c || op==0xf8c) {
                rt_log("nvn2: mesh shader uses overlapping native shared memory"); return nullptr;
            }
        }
        native.push_back(insn);
        const auto r = capture.Observe(insn, static_cast<uint32_t>(native.size() - 1));
        if (r != Shader::Ampere::ProgramCaptureState::Result::Continue) break;
    }
    uint32_t guest_local=0; if(mesh) std::memcpy(&guest_local,code+4,4); guest_local &= 0xffffff;
    auto lowered = Shader::Ampere::LowerToMaxwell(native, "full", false, mesh ? stage_memory : nullptr);
    if (!lowered && lowered.error == "native program uses lowering scratch registers" && gfx && (mesh || ((w0 >> 10) & 15) == 1)) {
        uint32_t local[3];
        std::memcpy(local, code + 4, sizeof local);
        if (!((local[0] | local[1] | local[2]) & 0xffffff) ||
            (mesh && guest_local<=4096 && !((local[1]|local[2]) & 0xffffff)))
            lowered = Shader::Ampere::LowerToMaxwell(native, "full", true, mesh ? stage_memory : nullptr, (guest_local+15)&~15u);
    }
    const auto eglantine_error = lowered.error;
    const uint32_t eglantine_error_offset = lowered.error_offset;
    // What the rest of this function takes from the lowering, from either lowerer.
    std::vector<uint64_t> lowered_code;
    std::vector<uint32_t> lowered_offsets;
    uint32_t lowered_spill = 0;
    if (lowered) {
        lowered_code = std::move(lowered.instructions);
        lowered_offsets = std::move(lowered.source_instruction_offsets);
        lowered_spill = lowered.local_spill_bytes;
    } else if (!mesh && !getenv("DKB_NO_LICHII_LOWER")) {
        // Lichii fallback. Mesh and task programs keep the Eglantine path: their stage memory layout is ours.
        namespace L = Shader::AmpereLichii;
        std::vector<L::Instruction> lnative;
        L::ProgramCaptureState lcapture;
        for (uint32_t at = hdr; at + 16 <= code_len; at += 16) {
            L::Instruction insn;
            std::memcpy(insn.words.data(), code + at, 16);
            lnative.push_back(insn);
            if (lcapture.Observe(insn, static_cast<uint32_t>(lnative.size() - 1)) != L::ProgramCaptureState::Result::Continue)
                break;
        }
        // Tensor-core programs (HMMA/IMMA/DMMA: Ocarina's neural-network passes) become a software matrix loop here.
        // They cost ~330 ms per frame on an RX 7900 XTX and were blocked before, so they stay blocked unless
        // DKB_LICHII_TENSOR=1.
        bool tensor = false;
        for (const auto &insn : lnative) {
            const uint32_t op = insn.Bits(0, 12);
            tensor |= op == 0x23c || op == 0x237 || op == 0x23f;
        }
        if (tensor && !getenv("DKB_LICHII_TENSOR")) {
            rt_log("nvn2: shader %016llx uses tensor instructions: Lichii fallback skipped (DKB_LICHII_TENSOR=1 allows it)",
                   (unsigned long long)gfx_shader_nvn2_hash(control, code));
            lnative.clear();
        }
        L::LoweringOptions options{};
        options.geometry = gfx && ((w0 >> 10) & 15) == 4;
        L::LoweredProgram alt;
        if (!lnative.empty()) alt = L::LowerToMaxwell(lnative, options);
        else alt.error = "skipped";
        // Lichii's banked register copy (MOV with an empty write mask and 0b1010 in bits 44-47) addresses registers
        // past R255 that only Lichii's Maxwell frontend has; the translator here would read a different register.
        bool banked = false;
        for (uint64_t insn : alt.instructions)
            banked |= (insn >> 48) == 0x5c98 && ((insn >> 39) & 15) == 0 && ((insn >> 44) & 15) == 10;
        if (alt && !banked) {
            static std::atomic<int> logged{0};
            if (logged++ < 64)
                rt_log("nvn2: shader %016llx stage %u lowered by the Lichii fallback (Eglantine: %.*s at +%#x)",
                       (unsigned long long)gfx_shader_nvn2_hash(control, code), gfx ? (w0 >> 10) & 15 : 0,
                       (int)eglantine_error.size(), eglantine_error.data(), eglantine_error_offset);
            lowered_code = std::move(alt.instructions);
            lowered_offsets = std::move(alt.source_instruction_offsets);
        } else if (alt && banked) {
            rt_log("nvn2: shader %016llx Lichii fallback lowered it with banked registers past R255: rejected",
                   (unsigned long long)gfx_shader_nvn2_hash(control, code));
        } else if (!alt && !lnative.empty()) {
            rt_log("nvn2: shader %016llx Lichii fallback also failed at +%#x: %.*s",
                   (unsigned long long)gfx_shader_nvn2_hash(control, code), alt.error_offset,
                   (int)alt.error.size(), alt.error.data());
        }
    }
    if (lowered_code.empty()) {
        // The rejected native instruction itself (four 32-bit words, opcode in bits 0-11), so the missing lowering
        // form can be read from the log without a shader dump.
        uint32_t words[4]{};
        if (eglantine_error_offset / 16 < native.size())
            std::memcpy(words, native[eglantine_error_offset / 16].words.data(), sizeof words);
        rt_log("nvn2: shader %016llx stage %u%s Ampere lowering failed at +%#x: %.*s (insn %08x %08x %08x %08x)",
               (unsigned long long)gfx_shader_nvn2_hash(control, code), gfx ? (w0 >> 10) & 15 : 0,
               mesh ? (task ? " task" : " mesh") : "", eglantine_error_offset, (int)eglantine_error.size(),
               eglantine_error.data(), words[0], words[1], words[2], words[3]);
        return nullptr;
    }

    auto *out = new Lowered;
    auto &m = out->code;
    // The lowering places instruction 0 at 0x10 modulo 32 with a scheduling word at every 32-byte boundary. Ryujinx
    // decodes from the code start (graphics: SPH+0x50, compute: 0) and takes every 32-byte boundary counted from there
    // as a scheduling word, so the code starts with a scheduling word and a NOP and instruction 0 lands 0x10 in. For
    // graphics, the 0x30 bytes the host skips and the first 0x50 bytes of the SPH come first. (Instruction 0 straight
    // at SPH+0x50 was decoded as a scheduling word and shifted every group: one real instruction in four was lost.)
    if (gfx && !mesh) {
        m.assign(6, 0);
        m.resize(16);
        std::memcpy(m.data() + 6, code, 0x50);
        if (lowered_spill) {
            auto *header = reinterpret_cast<uint32_t *>(m.data() + 6);
            header[1] = (header[1] & 0xff000000) | lowered_spill;
        }
    }
    m.push_back(0), m.push_back(kMaxwellNop);
    size_t pos = 0x10;   // from the code start
    // A full scheduling group of EXITs closes the program: Ryujinx's decoder runs on until a block ends, and a lowered
    // program whose last native instruction is a conditional exit or a self-branch would read past the buffer.
    // The compiler's end marker, an unconditional branch to itself after the last EXIT, becomes an EXIT too: Ryujinx's
    // structuring can join it to the exit path, and the empty endless loop it then emits hangs the GPU (device lost).
    for (size_t i = 0; i < lowered_code.size() + 4; i++) {
        if (pos % 32 == 0) m.push_back(0), pos += 8;
        uint64_t insn = i < lowered_code.size() ? lowered_code[i] : kMaxwellExit;
        if ((insn >> 52) == 0xe24 && ((insn >> 20) & 0xffffff) == 0xfffff8 && ((insn >> 16) & 15) == 7) insn = kMaxwellExit;
        m.push_back(insn), pos += 8;
    }

    // Inline constants (c[0x1]) follow the code in the NVN 2 buffer, from control +0x40 to +0x44; they go after the
    // Maxwell code, where control +0x700 points as in NVN 1. A BRX jump table in them holds native instruction offsets
    // (index * 16, as the lowering requires); the lowered BRX jumps to Maxwell addresses, so those are rewritten.
    uint32_t c1_at, c1_end;
    std::memcpy(&c1_at, control + 0x40, 4), std::memcpy(&c1_end, control + 0x44, 4);
    const uint32_t c1_off = static_cast<uint32_t>(m.size() * 8);
    if (c1_end > c1_at && c1_end - c1_at <= 0x10000) {
        std::vector<uint32_t> c1((c1_end - c1_at) / 4);
        std::memcpy(c1.data(), code + c1_at, c1.size() * 4);
        bool brx = false;
        for (const auto &insn : native) brx |= insn.Bits(0, 12) == 0x949 || insn.Bits(0, 12) == 0x958;
        // ponytail: any 16-aligned word inside the program counts as a table entry; an integer constant that happens to
        // be one would be rewritten too. Track the LDC base of each BRX if that ever bites.
        if (brx)
            for (uint32_t &w : c1)
                if (w % 16 == 0 && w / 16 < lowered_offsets.size()) {
                    const uint32_t i = lowered_offsets[w / 16];
                    // The lowering's address_of (0x50-based). Instruction i sits at address_of(i) - 0x40 from the code
                    // start, and the lowered BRX's base works out to -0x40, so the value lands on instruction i
                    // (Ryujinx FindBrxTargets: target = BRX base + table value).
                    w = 0x50 + i * 8 + ((i + 1) / 3) * 8;
                }
        c1.resize((c1.size() + 1) & ~size_t{1});
        m.resize(m.size() + c1.size() / 2);
        std::memcpy(m.data() + c1_off / 8, c1.data(), c1.size() * 4);
    }

    out->control.assign(kControl, 0);
    const uint32_t len = static_cast<uint32_t>(m.size() * 8);
    const uint32_t type = (w0 >> 10) & 15;   // SPH shader type -> NVN stage
    const uint32_t stage = !gfx ? 5 : type == 5 ? 1 : type == 4 ? 2 : type == 2 ? 3 : type == 3 ? 4 : 0;
    put32(out->control, 0x700, c1_off);
    put32(out->control, 0x704, len);
    put32(out->control, 0x714, mesh ? native_stage : stage);
    if (mesh) {
        static_assert(sizeof mesh_info <= kC0Layout - NVN_MESH_META_OFFSET);
        std::memcpy(out->control.data()+NVN_MESH_META_OFFSET,&mesh_info,sizeof mesh_info);
        put32(out->control,0x754,std::max(guest_local,lowered_spill));
        put32(out->control,0x748,mesh_info.threads); put32(out->control,0x74c,1); put32(out->control,0x750,1);
    }
    if (!gfx) {
        std::memcpy(out->control.data() + 0x748, control + 0x58, 12);   // local size (NVN 2 control +0x58)
        // The compute driver bank is packed per program from these counts (gfx_shader.c, "NVN 2 compute c0"):
        // images +0xb6, uniform buffers +0xb1, storage buffers +0xb2, textures +0xb3.
        // DKC1 adds the eight root-table word counts. The marker and counts enter the code/cache hash, so an older
        // DKC0 translation cannot be reused with the new parameter-block layout.
        const uint8_t lay[8] = {'D', 'K', 'C', '1', control[0xb6], control[0xb1], control[0xb2], control[0xb3]};
        std::memcpy(out->control.data() + kC0Layout, lay, sizeof lay);
        // Shared memory bytes (NVN 2 control +0x64; Bananza's upscaling network uses 0x2a88): the translator sizes the
        // workgroup's shared array from it, and with 0 every LDS read back nothing.
        std::memcpy(out->control.data() + kC0Layout + 8, control + 0x64, 4);
        std::memcpy(out->control.data() + kC0Layout + 12, control + 0xa9, 8);
    }
    return out;
}
}  // namespace

// Called only for native stages that survived ProgramSetShaders unlowered.
// Correlate the first actual GPU use with the earlier translation diagnostic.
extern "C" void nvn2_note_failed_use(const uint8_t *control,const uint8_t *code,
                                    uint64_t program,unsigned stage,uint64_t frame) {
    std::lock_guard<std::mutex> g(lock);
    if (!failed_program_uses.emplace(program,stage).second) return;
    const uint64_t hash=gfx_shader_nvn2_hash(control,code);
    if (active_failed_shaders.insert(hash).second)
        rt_log("nvn2: active unlowered shader %016llx NVN stage %u program %llu first used at frame %llu; GPU work blocked",
            (unsigned long long)hash,stage,(unsigned long long)program,(unsigned long long)frame);
}

// 1 and the replacement control and code for an NVN 2 stage, 0 when it does not lower.
extern "C" int nvn2_lower(const uint8_t *control, const uint8_t *code, const uint8_t **out_control,
                          const uint8_t **out_code) {
    const uint64_t key = gfx_shader_nvn2_hash(control, code);
    if (!key) {
        failures.fetch_add(1, std::memory_order_relaxed);
        uint32_t w[6];
        std::memcpy(w, control + 0x30, sizeof w);
        rt_log("nvn2: stage with a control block of unexpected sizes (+0x30 %#x +0x38 %#x +0x44 %#x, code %p): not "
               "lowered", w[0], w[2], w[5], (const void *)code);
        return 0;
    }
    std::lock_guard<std::mutex> g(lock);
    auto [it, fresh] = cache.try_emplace(key, nullptr);
    if (fresh && (it->second = lower(control, code))) {
        it->second->origin = key;
        origins.emplace(reinterpret_cast<const uint8_t *>(it->second->code.data()), key);
    }
    if (fresh && !it->second) failures.fetch_add(1, std::memory_order_relaxed);
    if (!it->second) return 0;
    *out_control = it->second->control.data();
    *out_code = reinterpret_cast<const uint8_t *>(it->second->code.data());
    return 1;
}

extern "C" uint64_t nvn2_lower_failures(void) { return failures.load(std::memory_order_relaxed); }

// The dump name (gfx_shader_nvn2_hash) of the NVN 2 stage a lowered code buffer came from, or 0. Lowered buffers live
// for the process, so their addresses never name another stage.
extern "C" uint64_t nvn2_origin(const uint8_t *code) {
    std::lock_guard<std::mutex> g(lock);
    auto it = origins.find(code);
    return it == origins.end() ? 0 : it->second;
}

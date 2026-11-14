"""Run the real framegen_record against instrumented GPU/provider stubs.

Exercise Auto and fixed rates, all providers, dialogue entry, long conversations,
exit, repeated events, and a host without the optional event callback.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUN_ALL_ARGS = ['--cxx', '{cxx}', '--headers', '{vulkan_headers}']


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


PREFIX = r'''
#define VK_USE_64_BIT_PTR_DEFINES 0
#include <vulkan/vulkan.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <initializer_list>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <utility>
#include "vk_present_rect.h"
using namespace mkwvk;
using VmaAllocation = void*;
constexpr int kMaxMult = 8;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"FAIL:%d %s\n",__LINE__,#x);std::exit(1); } } while(0)
struct { int framegen=2; } opts;
enum class FgMaker { None, BuiltIn, Dlss, Fsr3 };
static bool event_active;
static int event_changes, provider, provider_calls, synthetic_passes, scene, counter;
static FgMaker maker;
static int64_t clock_ns=1000000000;
static std::unordered_map<uint64_t,int> pixels;
static int story() { return event_active; }
static void diagnostic(const char*,const char*) { event_changes++; }
struct Host { int (*story_event_active)();void (*diagnostics_event)(const char*,const char*); } host_value{story,diagnostic};
static Host* host=&host_value;
static void logf(const char*,...) {}
static int64_t now_ns() { return clock_ns; }
static int display_refresh_mhz() { return 120000; }
static uint64_t reflex_frame() { return 0; }
static uint64_t antilag_frame() { return 0; }
'''

STUBS = r'''
static bool init() { return true; }
static bool ensure_size(VkCommandBuffer,uint32_t w,uint32_t h) { fg.w=w;fg.h=h;return true; }
static void full_barrier(VkCommandBuffer) {}
static void display_main() {}
static void note_maker(FgMaker m) { maker=m; }
static void pass(VkCommandBuffer,const Pipe& p,std::initializer_list<std::pair<VkImageView,VkSampler>> bindings,
                 uint32_t,uint32_t,const void* =nullptr,uint32_t=0) {
    auto b=bindings.begin();
    if (&p==&fg.copy) pixels[(b+1)->first]=scene;
    if (&p==&fg.flow || &p==&fg.synth || &p==&fg.median) synthetic_passes++;
    if (&p==&fg.synth) pixels[(b+3)->first]=-1;
}
static void vkCmdCopyImage(VkCommandBuffer,VkImage from,VkImageLayout,VkImage to,VkImageLayout,uint32_t,const VkImageCopy*) {
    pixels[to]=pixels.at(from);
}
static int dlss_fg_frames(VkCommandBuffer,VkImage,VkImageView,uint32_t,uint32_t,int count,
                          const VkImage* out,const VkImageView*,bool blend,uint64_t) {
    provider_calls++;
    if(provider!=1 || !blend) return 0;
    for(int k=0;k<count;k++) pixels[out[k]]=-1;
    return count;
}
namespace fsr3fi { static bool frames_wanted() { return provider==2; } }
static int fsr3fi_frame(VkCommandBuffer,OutSet& set,int,uint32_t,uint32_t,uint64_t) {
    provider_calls++;pixels[set.frame[0].image]=-1;return 1;
}
'''

MAIN = r'''
static void reset(int rate,int backend) {
    opts.framegen=rate;provider=backend;event_active=false;event_changes=0;
    host=&host_value;host_value.story_event_active=story;
    fg.have_prev=false;fg.story_protected=false;fg.thread_started=true;fg.next_set=0;fg.cur=0;
    fg.mult=rate==1?4:rate;fg.last_at=0;fg.slot_next=0;fg.game_ns=0;
    uint64_t id=10;
    for(auto& x:fg.frames) x.image=x.view=id++;
    for(auto& x:fg.lumas) x.image=x.view=id++;
    for(auto& x:fg.flows) x.image=x.view=id++;
    for(auto& s:fg.sets) { s.busy=false;for(auto& x:s.frame) x.image=x.view=id++; }
}
static void frame(bool event,bool real_only) {
    event_active=event;clock_ns+=33333333;scene=++counter;
    provider_calls=synthetic_passes=0;
    CHECK(framegen_record(VK_NULL_HANDLE,1,1280,720,nullptr));
    auto& s=*fg.recorded;
    if(real_only) {
        CHECK(s.made==0 && maker==FgMaker::None && synthetic_passes==0);
        CHECK(pixels.at(s.frame[0].image)==scene);
        if(opts.framegen==1) CHECK(s.shown==1 && s.game[0]);
        else CHECK(s.shown==-1);
        if(event) CHECK(provider_calls==0);
    } else {
        CHECK(s.made>0 && maker!=FgMaker::None);
        CHECK(pixels.at(s.frame[0].image)==-1);
    }
    s.busy=false;
}
int main() {
    for(int rate:{1,2,4,8}) for(int backend:{0,1,2}) {
        reset(rate,backend);
        frame(false,true);frame(false,false);
        for(int repeat=0;repeat<3;repeat++) {
            frame(true,true);
            for(int k=0;k<30;k++) frame(true,true);
            frame(false,true); // do not interpolate the last dialogue into gameplay
            frame(false,false);
        }
        CHECK(event_changes==6);
        CHECK(opts.framegen==rate); // protection never changes the player's choice
    }
    reset(2,0);host_value.story_event_active=nullptr;
    frame(false,true);frame(true,false);CHECK(event_changes==0);
    reset(2,0);host=nullptr;frame(false,true);frame(true,false);
    std::puts("PASS: actual dialogue frames, clean resume, Auto/2x/4x/8x, all providers, optional callback");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--headers', type=Path, required=True)
    args = parser.parse_args()
    source = (ROOT/'gpu/vk/vk_framegen.cpp').read_text(encoding='utf-8')
    structs = source[source.index('struct Img {'):source.index('// Used only by present_image')]
    unit = PREFIX + structs + STUBS + function(source, 'int auto_slots(') + function(source, 'bool framegen_record(') + MAIN
    host_source = (ROOT/'host/hos_main.c').read_text(encoding='utf-8')
    tick = function(host_source, 'static void oot_update_player_cheats(')
    assert 'const int story_event = oot_event_playing(c);' in tick
    assert '__atomic_store_n(&oot_story_event_active, story_event, __ATOMIC_RELAXED);' in tick
    assert '__atomic_load_n(&oot_story_event_active, __ATOMIC_RELAXED)' in function(host_source, 'int hos_oot_story_event_active(')
    with tempfile.TemporaryDirectory(prefix='framegen-dialogue-') as tmp:
        cpp, exe = Path(tmp)/'test.cpp', Path(tmp)/'test.exe'
        cpp.write_text(unit, encoding='utf-8')
        subprocess.run([args.cxx,'-std=c++20','-O2','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers',
                        '-DVK_NO_PROTOTYPES','-pthread','-I'+str(args.headers),'-I'+str(ROOT/'gpu/vk'),str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=20)


if __name__ == '__main__':
    main()

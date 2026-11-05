// Offline BSD service. Wire layouts are documented by libnx services/bsd.c.
// The no-transport policy follows nxnative dm/host/hle_net.c (MIT),
// revision 84dea69835414b18a4351cd45054bb611e0e3185.
// BSD IPC uses Linux errno/flag numbers, despite its FreeBSD ancestry (libnx
// runtime/devices/socket.c and Eglantine sockets/sockets.h). Do not use the
// host's errno numbers, or nxnative's direct SDK-return convention, on the wire.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ipc.h"
#include "platform/platform.h"

enum { BSD_BADF=9, BSD_AGAIN=11, BSD_INVAL=22, BSD_MFILE=24, BSD_NETDOWN=100,
       BSD_SEMAPHORE=1, BSD_NONBLOCK=0x800, BSD_CLOEXEC=0x80000,
       BSD_POLLIN=1, BSD_POLLOUT=4, BSD_POLLNVAL=0x20, BSD_FDS=256 };
typedef struct { uint64_t count; unsigned refs, descriptors, flags; } BsdEvent;
typedef struct { BsdEvent *event; unsigned cloexec; } BsdFd;
typedef struct { int32_t fd; int16_t events, revents; } BsdPoll;
_Static_assert(sizeof(BsdPoll)==8,"BSD pollfd wire size");
static BsdFd bsd_fds[BSD_FDS];
static PlatMutex bsd_lock=PLAT_MUTEX_INIT;
static PlatCond bsd_changed=PLAT_COND_INIT;

static void bsd_result(IpcResponse *rs,int32_t ret,int32_t error) {
    int32_t out[2]={ret,error}; ipc_out(rs,out,sizeof out);
}
static BsdEvent *bsd_lookup(int fd) {
    return fd>=0 && fd<BSD_FDS ? bsd_fds[fd].event : NULL;
}
static void bsd_release(BsdEvent *e) { if (e && !--e->refs) free(e); }
// All descriptors in this single guest process share the table, including
// cloned service sessions. A blocked operation pins its counter until return.
static int bsd_install(BsdEvent *e,unsigned cloexec) {
    for (int fd=0;fd<BSD_FDS;fd++) if (!bsd_fds[fd].event) {
        bsd_fds[fd]=(BsdFd){e,cloexec}; e->refs++; e->descriptors++; return fd;
    }
    return -1;
}
static IpcBuffer bsd_input(const IpcRequest *rq) {
    return rq->na && rq->a[0].size ? rq->a[0] : rq->nx ? rq->x[0] : (IpcBuffer){0};
}
static IpcBuffer bsd_output(const IpcRequest *rq) {
    return rq->nb && rq->b[0].size ? rq->b[0] : rq->nc ? rq->c[0] : (IpcBuffer){0};
}
static void bsd_written(const IpcRequest *rq,IpcResponse *rs,IpcBuffer b,uint64_t size) {
    if (!(rq->nb && rq->b[0].size) && rq->nc)
        rs->xout[rs->nxout++]=(IpcBuffer){b.addr,size,b.index};
}
static void bsd_event_io(const IpcRequest *rq,IpcResponse *rs,int write) {
    int fd=IPC_ARG(rq,int32_t,0);
    IpcBuffer buf=write ? bsd_input(rq) : bsd_output(rq);
    if (buf.size<8) { bsd_result(rs,-1,BSD_INVAL); return; }
    void *ptr=ipc_guest(buf.addr,8); uint64_t value=0;
    if (write) memcpy(&value,ptr,8);
    if (write && value==UINT64_MAX) { bsd_result(rs,-1,BSD_INVAL); return; }
    // Release the emulated CPU before acquiring a host lock that may sleep.
    __attribute__((cleanup(kern_core_back))) int away=kern_core_away();
    plat_mutex_lock(&bsd_lock);
    BsdEvent *e=bsd_lookup(fd);
    if (!e) { plat_mutex_unlock(&bsd_lock); bsd_result(rs,-1,BSD_BADF); return; }
    e->refs++;
    int error=0;
    while (write ? value>UINT64_MAX-1-e->count : !e->count) {
        if (!e->descriptors) { error=BSD_BADF; break; }
        if (e->flags & BSD_NONBLOCK) { error=BSD_AGAIN; break; }
        plat_cond_wait(&bsd_changed,&bsd_lock);
    }
    if (!error) {
        if (write) e->count+=value;
        else {
            value=e->flags & BSD_SEMAPHORE ? 1 : e->count;
            e->count-=value; memcpy(ptr,&value,8);
            bsd_written(rq,rs,buf,8);
        }
        plat_cond_broadcast(&bsd_changed);
    }
    bsd_release(e); plat_mutex_unlock(&bsd_lock);
    bsd_result(rs,error ? -1 : 8,error);
}
static void bsd_poll(const IpcRequest *rq,IpcResponse *rs) {
    int nfds=IPC_ARG(rq,int32_t,0),timeout=IPC_ARG(rq,int32_t,4);
    IpcBuffer in=bsd_input(rq),out=bsd_output(rq);
    if (nfds<0 || nfds>BSD_FDS || in.size<(uint64_t)nfds*8 || out.size<(uint64_t)nfds*8) {
        bsd_result(rs,-1,BSD_INVAL); return;
    }
    BsdPoll fds[BSD_FDS]; BsdEvent *pinned[BSD_FDS]={0};
    if (nfds) memcpy(fds,ipc_guest(in.addr,(uint64_t)nfds*8),(size_t)nfds*8);
    void *dst=nfds ? ipc_guest(out.addr,(uint64_t)nfds*8) : NULL;
    __attribute__((cleanup(kern_core_back))) int away=kern_core_away();
    uint64_t end=timeout<0 ? UINT64_MAX : plat_now_ns()+(uint64_t)timeout*1000000;
    plat_mutex_lock(&bsd_lock);
    for (int i=0;i<nfds;i++) {
        pinned[i]=bsd_lookup(fds[i].fd);
        if (pinned[i]) pinned[i]->refs++;
    }
    int ready;
    for (;;) {
        ready=0;
        for (int i=0;i<nfds;i++) {
            BsdEvent *e=pinned[i]; fds[i].revents=0;
            if (fds[i].fd<0) continue;
            if (!e || bsd_lookup(fds[i].fd)!=e) fds[i].revents=BSD_POLLNVAL;
            else {
                if (e->count && (fds[i].events & BSD_POLLIN)) fds[i].revents|=BSD_POLLIN;
                if (e->count<UINT64_MAX-1 && (fds[i].events & BSD_POLLOUT)) fds[i].revents|=BSD_POLLOUT;
            }
            if (fds[i].revents) ready++;
        }
        if (ready || !timeout) break;
        if (timeout<0) plat_cond_wait(&bsd_changed,&bsd_lock);
        else {
            uint64_t now=plat_now_ns(); if (now>=end) break;
            plat_cond_wait_ns(&bsd_changed,&bsd_lock,end-now);
        }
    }
    for (int i=0;i<nfds;i++) bsd_release(pinned[i]);
    plat_mutex_unlock(&bsd_lock);
    if (nfds) memcpy(dst,fds,(size_t)nfds*8);
    bsd_written(rq,rs,out,(uint64_t)nfds*8); bsd_result(rs,ready,0);
}

void bsd_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs) {
    switch (rq->cmd) {
    case 0: { // RegisterClient: configuration, PID, transfer memory size
        uint64_t size=IPC_ARG(rq,uint64_t,40);
        IpcTransferMemory *mem=rq->ncopy==1 ? kern_handle_get(rq->copy[0],KERN_TMEM) : NULL;
        if (!mem || !size || size>mem->size) { rs->result=IPC_R_BAD_HANDLE; return; }
        uint64_t pid=0x50; IPC_OUT(rs,pid); return;
    }
    case 1: return; // StartMonitoring: the client lifetime is its session lifetime
    case 36: { // SDK 18+ initialization negotiation, before StartMonitoring.
        // Eglantine BSD_USA::Unknown36 also accepts this scalar configuration;
        // accepting the library setup does not advertise a network connection.
        (void)IPC_ARG(rq,uint32_t,0);
        uint32_t accepted=0; IPC_OUT(rs,accepted); return;
    }
    case 2: case 3: { // Socket / SocketExempt: no network adapter is exposed
        bsd_result(rs,-1,BSD_NETDOWN); return;
    }
    case 6: bsd_poll(rq,rs); return;
    case 24: bsd_event_io(rq,rs,1); return;
    case 25: bsd_event_io(rq,rs,0); return;
    case 31: {
        uint64_t initial=IPC_ARG(rq,uint64_t,0); unsigned flags=IPC_ARG(rq,uint32_t,8);
        if (initial==UINT64_MAX || (flags & ~(BSD_SEMAPHORE|BSD_NONBLOCK|BSD_CLOEXEC))) {
            bsd_result(rs,-1,BSD_INVAL); return;
        }
        BsdEvent *e=calloc(1,sizeof *e);
        if (!e) { bsd_result(rs,-1,12); return; }
        e->count=initial; e->flags=flags & ~BSD_CLOEXEC;
        plat_mutex_lock(&bsd_lock); int fd=bsd_install(e,!!(flags & BSD_CLOEXEC));
        plat_mutex_unlock(&bsd_lock);
        if (fd<0) free(e);
        bsd_result(rs,fd,fd<0 ? BSD_MFILE : 0); return;
    }
    case 20: case 26: case 27: {
        int fd=IPC_ARG(rq,int32_t,0),ret=-1,error=0;
        plat_mutex_lock(&bsd_lock); BsdEvent *e=bsd_lookup(fd);
        if (!e) error=BSD_BADF;
        else if (rq->cmd==26) {
            bsd_fds[fd]=(BsdFd){0}; e->descriptors--; bsd_release(e); ret=0;
            plat_cond_broadcast(&bsd_changed);
        } else if (rq->cmd==27) {
            ret=bsd_install(e,0); if (ret<0) error=BSD_MFILE;
        } else {
            int cmd=IPC_ARG(rq,int32_t,4),flags=IPC_ARG(rq,int32_t,8);
            switch (cmd) {
            case 1: ret=bsd_fds[fd].cloexec; break; // F_GETFD
            case 2: bsd_fds[fd].cloexec=flags & 1; ret=0; break;
            case 3: ret=2 | (e->flags & BSD_NONBLOCK); break; // F_GETFL, O_RDWR
            case 4: e->flags=(e->flags & ~BSD_NONBLOCK) | (flags & BSD_NONBLOCK); ret=0;
                    plat_cond_broadcast(&bsd_changed); break;
            default: error=BSD_INVAL;
            }
        }
        plat_mutex_unlock(&bsd_lock); bsd_result(rs,ret,error); return;
    }
    default: ipc_unimplemented(s,rq);
    }
}

// Static retail environment metadata, as in nxnative hle_offline.c and
// Eglantine NSD::GetEnvironmentIdentifier. No hostname is resolved or contacted.
void nsd_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs) {
    if (rq->cmd==11) {
        int pointer=!(rq->nb && rq->b[0].size) && rq->nc;
        IpcBuffer b=pointer ? rq->c[0] : rq->nb ? rq->b[0] : (IpcBuffer){0};
        if (b.size<8) { rs->result=0xca01; return; }
        const char environment[8]="lp1";
        memcpy(ipc_guest(b.addr,8),environment,8);
        if (pointer) rs->xout[rs->nxout++]=(IpcBuffer){b.addr,8,b.index};
        return;
    }
    ipc_unimplemented(s,rq);
}

static int bsd_probe_call(unsigned cmd,const void *args,unsigned n,void *input,uint64_t insize,
                          void *output,uint64_t outsize,int expected_errno) {
    // The Windows stack may be above the 39-bit guest address limit under ASLR.
    void *gin=input ? mem_kernel_alloc(insize,8) : NULL;
    void *gout=output ? mem_kernel_alloc(outsize,8) : NULL;
    if (input) memcpy(gin,input,insize);
    if (output) memcpy(gout,output,outsize);
    IpcSession s={.name="bsd-probe"}; IpcResponse rs={0};
    IpcRequest rq={.cmd=cmd,.data=args,.data_size=n,
        .nx=!!input,.x={{(uint64_t)(uintptr_t)gin,insize,0}},
        .nc=!!output,.c={{(uint64_t)(uintptr_t)gout,outsize,0}}};
    bsd_handler(&s,&rq,&rs);
    if (output) { memcpy(output,gout,outsize); mem_kernel_free(gout,outsize); }
    if (input) mem_kernel_free(gin,insize);
    int32_t result[2]; memcpy(result,rs.data,8);
    if (rs.result || rs.data_size!=8 || result[1]!=expected_errno ||
        (expected_errno && result[0]!=-1) || (output && !expected_errno && rs.nxout!=1)) {
        fprintf(stderr,"probe-bsd: cmd %u returned %d errno %d, expected errno %d\n",
                cmd,result[0],result[1],expected_errno); return -999;
    }
    return result[0];
}
static int bsd_probe_open(uint64_t initial,unsigned flags) {
    struct { uint64_t count; uint32_t flags,pad; } args={initial,flags,0};
    return bsd_probe_call(31,&args,sizeof args,NULL,0,NULL,0,0);
}
typedef struct { int fd,write,result; uint64_t value; PlatEvent started; } BsdProbeIo;
static void bsd_probe_worker(void *arg) {
    BsdProbeIo *p=arg; plat_event_set(&p->started);
    p->result=bsd_probe_call(p->write ? 24 : 25,&p->fd,4,
        p->write ? &p->value : NULL,8,p->write ? NULL : &p->value,8,0);
}
static int bsd_probe_events(void) {
    int failed=0,fd=bsd_probe_open(3,BSD_NONBLOCK|BSD_CLOEXEC); uint64_t value=0;
    if (fd<0) return 1;
    failed+=bsd_probe_call(25,&fd,4,NULL,0,&value,8,0)!=8 || value!=3;
    failed+=bsd_probe_call(25,&fd,4,NULL,0,&value,8,BSD_AGAIN)!=-1;
    value=UINT64_MAX;
    failed+=bsd_probe_call(24,&fd,4,&value,8,NULL,0,BSD_INVAL)!=-1;
    value=UINT64_MAX-1;
    failed+=bsd_probe_call(24,&fd,4,&value,8,NULL,0,0)!=8;
    value=1; failed+=bsd_probe_call(24,&fd,4,&value,8,NULL,0,BSD_AGAIN)!=-1;
    BsdPoll fds[3]={{fd,BSD_POLLIN|BSD_POLLOUT,0},{-1,1,123},{999,1,0}},pollout[3];
    int32_t pargs[2]={3,0};
    failed+=bsd_probe_call(6,pargs,8,fds,sizeof fds,pollout,sizeof pollout,0)!=2 ||
        pollout[0].revents!=BSD_POLLIN || pollout[1].revents || pollout[2].revents!=BSD_POLLNVAL;
    failed+=bsd_probe_call(25,&fd,4,NULL,0,&value,7,BSD_INVAL)!=-1;
    int dup=bsd_probe_call(27,&fd,4,NULL,0,NULL,0,0); failed+=dup<0 || dup==fd;
    failed+=bsd_probe_call(26,&fd,4,NULL,0,NULL,0,0)!=0;
    failed+=bsd_probe_call(25,&dup,4,NULL,0,&value,8,0)!=8 || value!=UINT64_MAX-1;
    failed+=bsd_probe_call(26,&dup,4,NULL,0,NULL,0,0)!=0;
    failed+=bsd_probe_call(25,&dup,4,NULL,0,&value,8,BSD_BADF)!=-1;
    fd=bsd_probe_open(2,BSD_SEMAPHORE|BSD_NONBLOCK);
    failed+=bsd_probe_call(25,&fd,4,NULL,0,&value,8,0)!=8 || value!=1;
    failed+=bsd_probe_call(25,&fd,4,NULL,0,&value,8,0)!=8 || value!=1;
    failed+=bsd_probe_call(25,&fd,4,NULL,0,&value,8,BSD_AGAIN)!=-1;
    int32_t fc[3]={fd,4,0}; // make blocking through F_SETFL
    failed+=bsd_probe_call(20,fc,12,NULL,0,NULL,0,0)!=0;
    BsdProbeIo io={.fd=fd}; plat_event_init(&io.started,1,0);
    PlatThread *thread=plat_thread_new(bsd_probe_worker,&io,"eventfd-read-test");
    if (!thread) return 1;
    plat_event_wait(&io.started); value=7;
    failed+=bsd_probe_call(24,&fd,4,&value,8,NULL,0,0)!=8;
    plat_thread_join(thread); failed+=io.result!=8 || io.value!=1;
    failed+=bsd_probe_call(26,&fd,4,NULL,0,NULL,0,0)!=0;
    fd=bsd_probe_open(0,0); fds[0]=(BsdPoll){fd,BSD_POLLIN,0}; pargs[0]=1;pargs[1]=15;
    uint64_t start=plat_now_ns();
    failed+=bsd_probe_call(6,pargs,8,fds,8,pollout,8,0)!=0 || pollout[0].revents ||
        plat_now_ns()-start<15000000;
    io=(BsdProbeIo){.fd=fd,.write=1,.value=19}; plat_event_init(&io.started,1,0);
    thread=plat_thread_new(bsd_probe_worker,&io,"eventfd-poll-test");
    if (!thread) return 1;
    pargs[1]=1000;
    failed+=bsd_probe_call(6,pargs,8,fds,8,pollout,8,0)!=1 || pollout[0].revents!=BSD_POLLIN;
    plat_thread_join(thread); failed+=io.result!=8;
    failed+=bsd_probe_call(25,&fd,4,NULL,0,&value,8,0)!=8 || value!=19;
    failed+=bsd_probe_call(26,&fd,4,NULL,0,NULL,0,0)!=0;
    for (int i=0;i<BSD_FDS;i++) failed+=bsd_fds[i].event!=NULL;
    return failed;
}
int probe_bsd(void) {
    IpcSession s={.name="bsd:s"}; IpcRequest rq={.cmd=2}; IpcResponse rs={0};
    bsd_handler(&s,&rq,&rs); int32_t out[2]; memcpy(out,rs.data,sizeof out);
    int failed=rs.result || rs.data_size!=8 || out[0]!=-1 || out[1]!=BSD_NETDOWN;
    uint8_t config[48]={0}; rq.cmd=0; rq.data=config; rq.data_size=sizeof config;
    memset(&rs,0,sizeof rs); bsd_handler(&s,&rq,&rs);
    failed += rs.result!=IPC_R_BAD_HANDLE;
    uint8_t *environment=mem_kernel_alloc(9,8); memset(environment,0xa5,9);
    rq=(IpcRequest){.cmd=11,.nc=1,.c={{(uint64_t)(uintptr_t)environment,8,0}}};
    memset(&rs,0,sizeof rs); nsd_handler(&s,&rq,&rs);
    failed += rs.result || rs.nxout!=1 || memcmp(environment,"lp1\0\0\0\0",8) || environment[8]!=0xa5;
    rq.c[0].size=7; memset(&rs,0,sizeof rs); nsd_handler(&s,&rq,&rs);
    failed += rs.result!=0xca01;
    mem_kernel_free(environment,9);
    uint32_t version=3;
    rq=(IpcRequest){.cmd=5,.data=(const uint8_t *)&version,.data_size=4};
    memset(&rs,0,sizeof rs); ssl_handler(&s,&rq,&rs); failed += rs.result!=0;
    rq.cmd=1; memset(&rs,0,sizeof rs); ssl_handler(&s,&rq,&rs);
    failed += rs.result || rs.data_size!=4 || rs.data[0]!=0;
    failed+=bsd_probe_events();
    printf("probe-bsd: %s (offline services; eventfd counters, semaphore, overflow, duplicate, read wake and poll)\n",failed?"FAILED":"passed");
    return !!failed;
}

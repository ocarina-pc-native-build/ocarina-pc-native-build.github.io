// Offline Horizon network interface manager. Protocol reference: Eglantine
// src/core/hle/service/nifm/nifm.cpp at 23f383cab532bf3834ea55f3488b48841f3c727b.
// The port has no network transport yet: no interface, connection or accepted
// request is advertised. Unknown operations retain the runtime's named failure.
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "ipc.h"
#include "platform/platform.h"
#include "kernel.h"

#define NIFM_DISABLED (110u | (1111u<<9))
typedef struct {
    PlatMutex lock;
    uint32_t events[2],preset,state;
    uint8_t confirmation;
} NifmRequest;
static void request_close(void *state) {
    NifmRequest *r=state;
    for (unsigned i=0;i<2;i++) kern_handle_close(r->events[i]);
    free(r);
}
static void network_request(IpcSession *s,const IpcRequest *rq,IpcResponse *rs) {
    NifmRequest *r=s->state;
    plat_mutex_lock(&r->lock);
    switch (rq->cmd) {
    case 0: IPC_OUT(rs,r->state); break;
    case 1: rs->result=NIFM_DISABLED; break;
    case 2:
        for (unsigned i=0;i<2;i++) rs->copy[rs->ncopy++]=kern_event_readable(r->events[i]);
        break;
    case 3: case 4:
        // Offline requests complete immediately in NotSubmitted/Error (1).
        // Notify both state and result waiters; a request is never accepted.
        r->state=1;
        for (unsigned i=0;i<2;i++) kern_event_signal(r->events[i]);
        break;
    case 6: r->preset=IPC_ARG(rq,uint32_t,0); break;
    case 11: r->confirmation=IPC_ARG(rq,uint8_t,0); break;
    default: plat_mutex_unlock(&r->lock); ipc_unimplemented(s,rq);
    }
    plat_mutex_unlock(&r->lock);
}

static volatile int32_t next_client;
static void general_service(IpcSession *s,const IpcRequest *rq,IpcResponse *rs) {
    switch (rq->cmd) {
    case 1: {
        uint64_t id=(uint64_t)(uintptr_t)s->state;
        IpcBuffer b=rq->nc ? rq->c[0] : (IpcBuffer){0};
        if (b.size<sizeof id) { rs->result=0xca01; return; }
        memcpy(ipc_guest(b.addr,sizeof id),&id,sizeof id);
        rs->xout[rs->nxout++]=(IpcBuffer){b.addr,sizeof id,b.index}; return;
    }
    case 4: {
        NifmRequest *r=calloc(1,sizeof *r); if (!r) rt_fatal("nifm: request allocation");
        r->preset=IPC_ARG(rq,uint32_t,0); r->state=1;
        for (unsigned i=0;i<2;i++) r->events[i]=kern_event_new();
        rs->move[rs->nmove++]=ipc_session_new("nifm:IRequest",network_request,r,request_close); return;
    }
    case 17: case 20: case 21: case 22: {
        uint8_t available=0; IPC_OUT(rs,available); return;
    }
    case 18: { uint8_t status[3]={1,0,0}; ipc_out(rs,status,sizeof status); return; }
    case 33: return; // ConfirmSystemAvailability: the manager itself is available
    case 5: case 101: // GetCurrentNetworkProfile (old / SDK V2)
        // No active network profile exists while communications are disabled.
        // Do not return an invented successful profile or modify its output.
        rs->result=NIFM_DISABLED; return;
    default: ipc_unimplemented(s,rq);
    }
}

void nifm_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs) {
    if (rq->cmd==4 || rq->cmd==5) {
        uint32_t id=(uint32_t)plat_inc32(&next_client);
        rs->move[rs->nmove++]=ipc_session_new("nifm:IGeneralService",general_service,(void *)(uintptr_t)id,NULL);
        return;
    }
    ipc_unimplemented(s,rq);
}

int probe_nifm(void) {
    long before=ipc_sessions_live(); int failed=0; uint64_t last=0;
    for (int i=0;i<2;i++) {
        IpcSession root={.name="nifm:u"};
        IpcRequest rq={.cmd=(unsigned)(4+i)}; IpcResponse rs={0};
        nifm_handler(&root,&rq,&rs);
        if (rs.result || rs.nmove!=1) return 1;
        uint32_t handle=rs.move[0]; IpcSession *s=kern_session_acquire(handle);
        uint64_t *idbuf=mem_kernel_alloc(16,8); idbuf[0]=0; idbuf[1]=0x12345678;
        rq.cmd=1; rq.nc=1; rq.c[0]=(IpcBuffer){(uint64_t)(uintptr_t)idbuf,8,0};
        memset(&rs,0,sizeof rs); s->handler(s,&rq,&rs);
        uint64_t id=idbuf[0];
        failed += rs.result || rs.data_size || rs.nxout!=1 || !id || id==last || idbuf[1]!=0x12345678; last=id;
        mem_kernel_free(idbuf,16); rq.nc=0;
        const unsigned queries[]={17,20,21,22,18,33};
        for (unsigned j=0;j<sizeof queries/sizeof *queries;j++) {
            rq.cmd=queries[j]; memset(&rs,0,sizeof rs); s->handler(s,&rq,&rs);
            failed += rs.result!=0;
            if (rq.cmd==18) failed += rs.data_size!=3 || rs.data[1] || rs.data[2];
            else if (rq.cmd!=33) failed += rs.data_size!=1 || rs.data[0]!=0;
        }
        const unsigned profile_queries[]={5,101};
        for (unsigned j=0;j<2;j++) {
            rq.cmd=profile_queries[j]; memset(&rs,0,sizeof rs); s->handler(s,&rq,&rs);
            failed+=rs.result!=NIFM_DISABLED || rs.data_size || rs.nxout;
        }
        ipc_session_release(s); kern_handle_close(handle);
    }
    failed += ipc_sessions_live()!=before;
    printf("probe-nifm: %s (unique clients, offline queries, session cleanup)\n",failed?"FAILED":"passed");
    return !!failed;
}

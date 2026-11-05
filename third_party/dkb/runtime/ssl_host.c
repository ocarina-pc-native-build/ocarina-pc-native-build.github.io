// SSL library initialization for the offline host. Interface command layout
// checked against Eglantine ssl.cpp (23f383cab532bf3834ea55f3488b48841f3c727b).
// No TLS context or encrypted connection is advertised by this implementation.
#include "ipc.h"

void ssl_handler(IpcSession *s,const IpcRequest *rq,IpcResponse *rs) {
    switch (rq->cmd) {
    case 5: // SetInterfaceVersion is negotiation, not a TLS handshake.
        (void)IPC_ARG(rq,uint32_t,0); return;
    case 1: case 6: { // GetContextCount / FlushSessionCache: both empty
        uint32_t count=0; IPC_OUT(rs,count); return;
    }
    default: ipc_unimplemented(s,rq);
    }
}

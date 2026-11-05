#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <cstdio>
#include <cstring>
#include <string>
#include "host.h"

static HWND path_box,status_box;
static std::wstring exe_dir() {
    wchar_t p[32768]; DWORD n=GetModuleFileNameW(nullptr,p,32768);
    std::wstring s(p,n); return s.substr(0,s.find_last_of(L"\\/"));
}
static void diagnostics(HWND hwnd) {
    const auto dir=exe_dir()+L"\\logs";
    CreateDirectoryW(dir.c_str(),nullptr);
    const auto file=dir+L"\\diagnostics.txt";
    FILE *out=_wfopen(file.c_str(),L"wb");
    if(!out){MessageBoxW(hwnd,L"Cannot create diagnostic log.",L"Error",MB_ICONERROR);return;}
    fclose(out);
    // Run the diagnostic executable with inherited file handles. Paths are quoted;
    // no shell is involved and user-selected paths are never executable commands.
    HANDLE log=CreateFileW(file.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    SetHandleInformation(log,HANDLE_FLAG_INHERIT,HANDLE_FLAG_INHERIT);
    STARTUPINFOW si{}; si.cb=sizeof(si); si.dwFlags=STARTF_USESTDHANDLES|STARTF_USESHOWWINDOW;
    si.wShowWindow=SW_HIDE; si.hStdOutput=log; si.hStdError=log; si.hStdInput=GetStdHandle(STD_INPUT_HANDLE);
    PROCESS_INFORMATION pi{};
    std::wstring command=L"\""+exe_dir()+L"\\oot-runtime.exe\" --diagnostics";
    if(CreateProcessW(nullptr,command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW,nullptr,exe_dir().c_str(),&si,&pi)){
        CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
        SetWindowTextW(status_box,(L"Diagnostics running. Results: "+file+L"\r\nNo game code is launched.").c_str());
    }else SetWindowTextW(status_box,L"Failed to start diagnostics.");
    if(log!=INVALID_HANDLE_VALUE) CloseHandle(log);
}
static LRESULT CALLBACK proc(HWND hwnd,UINT msg,WPARAM w,LPARAM l) {
    if(msg==WM_CREATE){
        CreateWindowW(L"STATIC",L"OoT2026-PC-Recomp 0.1.0 — development runtime",WS_CHILD|WS_VISIBLE,20,18,690,25,hwnd,nullptr,nullptr,nullptr);
        CreateWindowW(L"STATIC",L"Game compatibility is unverified. A playable port is not included.",WS_CHILD|WS_VISIBLE,20,52,690,25,hwnd,nullptr,nullptr,nullptr);
        path_box=CreateWindowW(L"EDIT",L"Select the decrypted ExeFS folder",WS_CHILD|WS_VISIBLE|WS_BORDER|ES_READONLY,20,94,540,26,hwnd,nullptr,nullptr,nullptr);
        CreateWindowW(L"BUTTON",L"Choose folder",WS_CHILD|WS_VISIBLE,570,92,130,30,hwnd,(HMENU)1,nullptr,nullptr);
        CreateWindowW(L"BUTTON",L"Run diagnostics",WS_CHILD|WS_VISIBLE,20,145,180,34,hwnd,(HMENU)2,nullptr,nullptr);
        CreateWindowW(L"BUTTON",L"Open logs",WS_CHILD|WS_VISIBLE,215,145,140,34,hwnd,(HMENU)3,nullptr,nullptr);
        status_box=CreateWindowW(L"EDIT",L"Native host: memory, threads, TLS and clock.\r\nVulkan 1.3 GPU transfer/readback test; SDL3 controller enumeration.\r\nNVN2 game rendering and Horizon service integration are not connected.\r\nUse tools/inspect_dump.py for module validation and analysis.",WS_CHILD|WS_VISIBLE|WS_BORDER|ES_READONLY|ES_MULTILINE,20,200,680,130,hwnd,nullptr,nullptr,nullptr);
        return 0;
    }
    if(msg==WM_COMMAND){
        if(LOWORD(w)==1){
            BROWSEINFOW bi{};bi.hwndOwner=hwnd;bi.lpszTitle=L"Choose decrypted ExeFS";bi.ulFlags=BIF_RETURNONLYFSDIRS|BIF_NEWDIALOGSTYLE;
            PIDLIST_ABSOLUTE id=SHBrowseForFolderW(&bi);
            if(id){wchar_t path[MAX_PATH];if(SHGetPathFromIDListW(id,path)) SetWindowTextW(path_box,path);CoTaskMemFree(id);}
        }else if(LOWORD(w)==2) diagnostics(hwnd);
        else if(LOWORD(w)==3){auto p=exe_dir()+L"\\logs";CreateDirectoryW(p.c_str(),nullptr);ShellExecuteW(hwnd,L"open",p.c_str(),nullptr,nullptr,SW_SHOWNORMAL);}
        return 0;
    }
    if(msg==WM_DESTROY){PostQuitMessage(0);return 0;}
    return DefWindowProcW(hwnd,msg,w,l);
}
int main(int argc,char **argv) {
    if(argc>1){
        if(!strcmp(argv[1],"--self-test")) return oot_selftest();
        if(!strcmp(argv[1],"--probe-vulkan")) return oot_probe_gpu(argc>2 && !strcmp(argv[2],"--validate"));
        if(!strcmp(argv[1],"--probe-input")) return oot_probe_input();
        if(!strcmp(argv[1],"--diagnostics")){int h=oot_selftest(),g=oot_probe_gpu(0),i=oot_probe_input();return h||g||i;}
        if(!strcmp(argv[1],"--version")){puts("OoT2026-PC-Recomp 0.1.0; standalone diagnostic runtime; game support unverified");return 0;}
        fputs("Usage: oot-runtime [--self-test|--probe-vulkan [--validate]|--probe-input|--diagnostics|--version]\nGame execution is not implemented.\n",stderr);return 2;
    }
    CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    WNDCLASSW wc{};wc.lpfnWndProc=proc;wc.hInstance=GetModuleHandleW(nullptr);wc.lpszClassName=L"OoT2026Runtime";wc.hCursor=LoadCursorW(nullptr,IDC_ARROW);wc.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);
    RegisterClassW(&wc);
    HWND win=CreateWindowW(wc.lpszClassName,L"OoT2026-PC-Recomp — Runtime diagnostics",WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX,CW_USEDEFAULT,CW_USEDEFAULT,750,390,nullptr,nullptr,wc.hInstance,nullptr);
    if(!win){CoUninitialize();return 1;}
    ShowWindow(win,SW_SHOW);MSG msg{};while(GetMessageW(&msg,nullptr,0,0)>0){TranslateMessage(&msg);DispatchMessageW(&msg);}CoUninitialize();return 0;
}

// SPDX-License-Identifier: MIT
// Turn the existing workgroup IR's stage-memory body into a real MeshEXT entry.
// The body remains a function: every early return rejoins the uniform export.
// NVN layout reference: nxnative dmsh_meshstage.py, commit 84dea69835414b18a4351cd45054bb611e0e3185.
// SPIR-V execution model and output rules: SPV_EXT_mesh_shader (Khronos).
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;

static class MeshExport
{
    sealed class Builder
    {
        public uint Next;
        public readonly List<uint[]> Types = new(), Decorations = new(), Globals = new(), Body = new();
        readonly Dictionary<string,uint> types = new();
        public uint Id() => Next++;
        public static uint[] Op(uint op, params uint[] a) => new[]{((uint)a.Length+1)<<16|op}.Concat(a).ToArray();
        public uint Type(uint op, params uint[] args)
        {
            string k=op+":"+string.Join(",",args);
            if(types.TryGetValue(k,out uint id)) return id;
            id=Id(); types[k]=id; Types.Add(Op(op,new[]{id}.Concat(args).ToArray())); return id;
        }
        public void Import(uint[] w)
        {
            uint op=w[0]&65535;
            if(op>=19 && op<=33) types[op+":"+string.Join(",",w.Skip(2))]=w[1];
        }
        public uint Constant(uint type,uint value)
        {
            foreach(var w in Types) if((w[0]&65535)==43 && w[1]==type && w[3]==value)return w[2];
            uint id=Id();Types.Add(Op(43,type,id,value));return id;
        }
        public uint Result(uint op,uint type,params uint[] args)
        { uint id=Id();Body.Add(Op(op,new[]{type,id}.Concat(args).ToArray()));return id; }
        public uint Variable(uint type,uint storage)
        {uint id=Id();Globals.Add(Op(59,type,id,storage));return id;}
        public void Emit(uint op,params uint[] args)=>Body.Add(Op(op,args));
        public void Decorate(uint id,uint decoration,params uint[] args)=>Decorations.Add(Op(71,new[]{id,decoration}.Concat(args).ToArray()));
    }

    public static byte[] Wrap(byte[] code,JsonObject job,out int indirectBinding)
    {
        var m=job["mesh"]?.AsObject() ?? throw new InvalidDataException("MeshEXT requires mesh metadata");
        int Get(string k)=>m[k]?.GetValue<int>() ?? throw new InvalidDataException("Missing mesh "+k);
        bool task=(string)job["stage"]=="ts", usesTask=Get("uses_task")!=0;
        int payload=Get("payload");
        int threads=Get("threads"),vertices=Get("vertices"),primitives=Get("primitives");
        int shared=Get("shared"),output=Get("output"),prim=Get("primitive");
        int[] attrs=m["attributes"].AsArray().Select(x=>x.GetValue<int>()).ToArray();
        if(Get("version")!=1 || threads!=32 || payload<0 || payload>16384 || (!task && (vertices<=0 || vertices>256 || vertices%32!=0 ||
           primitives<=0 || primitives>255 || shared<=0 || shared>32768 || shared%128!=0 ||
           output<16 || output%4!=0 || prim<output || prim%4!=0 || prim+4+3*primitives>shared ||
           attrs.Length<4 || attrs.Length>132 || attrs.Distinct().Count()!=attrs.Length ||
           attrs.Any(x=>x<0 || x>131) || !Enumerable.Range(128,4).All(attrs.Contains))))
            throw new NotSupportedException("Unsupported mesh output contract");
        if(!task && output+((Math.Max(vertices,primitives)+31)/32)*attrs.Length*128>prim)
            throw new InvalidDataException("Mesh attribute and primitive regions overlap");
        uint[] words=MemoryMarshal.Cast<byte,uint>(code).ToArray();
        var records=new List<uint[]>();
        for(int at=5;at<words.Length;){int n=(int)(words[at]>>16);if(n<1 || at+n>words.Length)throw new InvalidDataException("Invalid body SPIR-V");records.Add(words[at..(at+n)]);at+=n;}
        var b=new Builder{Next=words[3]};foreach(var w in records)b.Import(w);
        // MeshEXT requires SPIR-V 1.4. Upgrade the old SSBO representation
        // (Uniform + BufferBlock) to StorageBuffer + Block, including derived
        // access-chain pointer types. UBO pointers keep Uniform storage.
        var bufferBlocks=records.Where(w=>(w[0]&65535)==71 && w[2]==3).Select(w=>w[1]).ToHashSet();
        var pointers=records.Where(w=>(w[0]&65535)==32).ToDictionary(w=>w[1],w=>w[3]);
        var storagePointers=new HashSet<uint>();
        foreach(var w in records)
        {
            uint op=w[0]&65535;
            if(op==71 && w[2]==3)w[2]=2;
            if(op==59 && w[3]==2 && pointers.TryGetValue(w[1],out uint pointee) && bufferBlocks.Contains(pointee))
            {w[1]=b.Type(32,12,pointee);w[3]=12;storagePointers.Add(w[2]);}
            if(op is 65 or 66 or 67 && storagePointers.Contains(w[3]))
            {w[1]=b.Type(32,12,pointers[w[1]]);storagePointers.Add(w[2]);}
        }
        uint[] entry=records.Single(w=>(w[0]&65535)==15);
        if(entry[1]!=5)throw new InvalidDataException("Mesh body must use the workgroup IR");
        uint oldMain=entry[2],main=b.Id();
        int firstFunction=records.FindIndex(w=>(w[0]&65535)==54);
        var globals=records.Take(firstFunction).Where(w=>(w[0]&65535)==59).ToList();
        uint[] sm=globals.Single(w=>w[3]==4);
        uint ptrType=sm[1],memory=sm[2];
        uint arrayType=records.Single(w=>(w[0]&65535)==32 && w[1]==ptrType)[3];
        uint[] array=records.Single(w=>(w[0]&65535)==28 && w[1]==arrayType);
        uint u32=b.Type(21,32,0),f32=b.Type(22,32),v4=b.Type(23,f32,4),v3u=b.Type(23,u32,3);
        if(array[2]!=u32)throw new InvalidDataException("Mesh stage memory must contain uint32 words");
        uint declared=records.Single(w=>(w[0]&65535)==43 && w[2]==array[3])[3];
        if(declared!=(uint)shared/4)throw new InvalidDataException("Mesh shared memory size mismatch");
        uint boolean=b.Type(20),voidType=b.Type(19),fnType=b.Type(33,voidType);
        uint wgPtr=b.Type(32,4,u32),inputPtr=b.Type(32,1,u32),inputV3Ptr=b.Type(32,1,v3u);
        uint c(uint v)=>b.Constant(u32,v);
        uint LocalBuiltin(uint builtin,uint type,uint pointer)
        {
            var d=records.FirstOrDefault(w=>(w[0]&65535)==71 && w.Length>=4 && w[2]==11 && w[3]==builtin);
            if(d!=null)return d[1];uint id=b.Variable(pointer,1);b.Decorate(id,11,builtin);return id;
        }
        uint lidVar=LocalBuiltin(29,u32,inputPtr),groupVar=LocalBuiltin(26,v3u,inputV3Ptr);
        indirectBinding=(int)records.Where(w=>(w[0]&65535)==71 && w[2]==33).Select(w=>w[3]).DefaultIfEmpty(0u).Max()+1;
        uint argumentVector=b.Type(23,u32,4),argumentStruct=b.Type(30,argumentVector);
        b.Decorate(argumentStruct,2);b.Decorations.Add(Builder.Op(72,argumentStruct,0,35,0));
        uint argumentVar=b.Variable(b.Type(32,2,argumentStruct),2),argumentPtr=b.Type(32,2,u32);
        b.Decorate(argumentVar,34,0);b.Decorate(argumentVar,33,(uint)indirectBinding);
        uint pushStruct=b.Type(30,u32,u32);b.Decorate(pushStruct,2);
        b.Decorations.Add(Builder.Op(72,pushStruct,0,35,0));
        b.Decorations.Add(Builder.Op(72,pushStruct,1,35,4));
        uint push=b.Variable(b.Type(32,9,pushStruct),9),pushPtr=b.Type(32,9,u32);
        var outputs=new Dictionary<int,uint>(); uint indices=0,indexPtr=0,outElement=0;
        if(!task) {
        uint outArray=b.Type(28,v4,c((uint)vertices)),outPtr=b.Type(32,3,outArray);outElement=b.Type(32,3,v4);
        foreach(int loc in attrs.Select(a=>a>=128?-1:a/4).Distinct())
        {uint id=b.Variable(outPtr,3);if(loc<0)b.Decorate(id,11,0);else b.Decorate(id,30,(uint)loc);outputs[loc]=id;}
        indices=b.Variable(b.Type(32,3,b.Type(28,v3u,c((uint)primitives))),3);
        b.Decorate(indices,11,5296);b.Decorate(indices,5271);
        indexPtr=b.Type(32,3,v3u);
        }
        uint payloadVar=0,payloadPtr=0;
        if(task || usesTask) {
            uint t=b.Type(28,u32,c((uint)(payload+3)/4));
            payloadVar=b.Variable(b.Type(32,5402,t),5402);payloadPtr=b.Type(32,5402,u32);
        }
        b.Emit(54,voidType,main,0,fnType);b.Emit(248,b.Id());
        uint lid=b.Result(61,u32,lidVar),group=b.Result(61,v3u,groupVar);
        uint groupX=b.Result(81,u32,group,0);
        uint first=b.Result(61,u32,b.Result(65,pushPtr,push,c(0)));
        uint isIndirect=b.Result(171,boolean,b.Result(61,u32,b.Result(65,pushPtr,push,c(1))),c(0));
        uint bufferFirst=b.Result(61,u32,b.Result(65,argumentPtr,argumentVar,c(0),c(3)));
        first=b.Result(169,u32,isIndirect,bufferFirst,first);
        uint add(uint a,uint d)=>b.Result(128,u32,a,d);
        uint load(uint at)=>b.Result(61,u32,b.Result(65,wgPtr,memory,at));
        void store(uint at,uint value)=>b.Emit(62,b.Result(65,wgPtr,memory,at),value);
        // The complete workgroup initializes stage memory before any native instruction.
        for(uint at=0;at<(uint)shared/4;at+=32)store(add(lid,c(at)),c(0));
        b.Emit(224,c(2),c(2),c(264));
        uint isLeader=b.Result(170,boolean,lid,c(0)),leader=b.Id(),joined=b.Id();
        b.Emit(247,joined,0);b.Emit(250,isLeader,leader,joined);b.Emit(248,leader);
        store(c(0),usesTask && !task ? groupX : add(first,groupX));b.Emit(249,joined);b.Emit(248,joined);
        if(usesTask && !task) {
            CopyPayload(false);
            b.Emit(224,c(2),c(2),c(264));
            uint yes=b.Id(),end=b.Id();b.Emit(247,end,0);b.Emit(250,isLeader,yes,end);b.Emit(248,yes);
            store(c(4),groupX);b.Emit(249,end);b.Emit(248,end);
        }
        b.Emit(224,c(2),c(2),c(264));
        b.Result(57,voidType,oldMain);
        b.Emit(224,c(2),c(2),c(264));
        void CopyPayload(bool write) {
            for(uint at=0;at<(uint)(payload+3)/4;at+=32) {
                uint i=add(lid,c(at)),yes=b.Id(),end=b.Id();
                uint valid=b.Result(176,boolean,i,c((uint)(payload+3)/4));
                b.Emit(247,end,0);b.Emit(250,valid,yes,end);b.Emit(248,yes);
                uint ptr=b.Result(65,payloadPtr,payloadVar,i);
                if(write)b.Emit(62,ptr,load(add(i,c((uint)output/4))));
                else store(add(i,c(4)),b.Result(61,u32,ptr));
                b.Emit(249,end);b.Emit(248,end);
            }
        }
        if(task) {
            CopyPayload(true);
            b.Emit(5294,load(c((uint)output/4+1)),c(1),c(1),payloadVar);
        } else {
        uint np=b.Result(194,u32,load(c((uint)prim/4)),c(24));
        uint within=b.Result(178,boolean,np,c((uint)primitives));
        np=b.Result(169,u32,within,np,c((uint)primitives));
        b.Emit(5295,c((uint)vertices),np);
        // Output component blocks each contain one word per lane, in SPH OMAP order.
        for(uint block=0;block<(uint)vertices/32;block++)
        {
            uint vertex=add(lid,c(block*32));
            foreach(var item in outputs)
            {
                uint[] components=new uint[4];
                for(int k=0;k<4;k++)
                {
                    int attr=item.Key<0?128+k:item.Key*4+k,comp=Array.IndexOf(attrs,attr);
                    uint val=comp<0?c(k==3?0x3f800000u:0):load(add(lid,c((uint)output/4+block*(uint)attrs.Length*32+(uint)comp*32)));
                    components[k]=b.Result(124,f32,val);
                }
                uint value=b.Result(80,v4,components);
                b.Emit(62,b.Result(65,outElement,item.Value,vertex),value);
            }
        }
        for(uint block=0;block<((uint)primitives+31)/32;block++)
        {
            uint i=add(lid,c(block*32)),valid=b.Result(176,boolean,i,np),yes=b.Id(),merge=b.Id();
            b.Emit(247,merge,0);b.Emit(250,valid,yes,merge);b.Emit(248,yes);
            uint[] values=new uint[3];
            for(uint k=0;k<3;k++)
            {
                uint at=add(b.Result(132,u32,i,c(3)),c((uint)prim+4+k));
                uint w=load(b.Result(194,u32,at,c(2)));
                uint shift=b.Result(132,u32,b.Result(199,u32,at,c(3)),c(8));
                values[k]=b.Result(199,u32,b.Result(194,u32,w,shift),c(255));
            }
            b.Emit(62,b.Result(65,indexPtr,indices,i),b.Result(80,v3u,values));
            b.Emit(249,merge);b.Emit(248,merge);
        }
        b.Emit(253);
        }
        b.Emit(56);
        var result=new List<uint>{words[0],0x00010400,words[2],b.Next,words[4]};
        void Append(IEnumerable<uint[]> list){foreach(var w in list)result.AddRange(w);}
        Append(records.Where(w=>(w[0]&65535)==17));result.AddRange(Builder.Op(17,5283));
        Append(records.Where(w=>(w[0]&65535)==10));
        uint[] str(string s){byte[] bytes=Encoding.UTF8.GetBytes(s+"\0");Array.Resize(ref bytes,(bytes.Length+3)&~3);return MemoryMarshal.Cast<byte,uint>(bytes).ToArray();}
        result.AddRange(Builder.Op(10,str("SPV_EXT_mesh_shader")));
        Append(records.Where(w=>(w[0]&65535)==11 || (w[0]&65535)==14));
        uint[] interfaces=globals.Concat(b.Globals).Select(w=>w[2]).ToArray();
        result.AddRange(Builder.Op(15,new uint[]{task ? 5364u : 5365u,main}.Concat(str("main")).Concat(interfaces).ToArray()));
        result.AddRange(Builder.Op(16,main,17,32,1,1));if(!task) { result.AddRange(Builder.Op(16,main,26,(uint)vertices));
        result.AddRange(Builder.Op(16,main,5270,(uint)primitives));result.AddRange(Builder.Op(16,main,5298)); }
        Append(records.Take(firstFunction).Where(w=>(w[0]&65535)>=2 && (w[0]&65535)<=9));
        Append(records.Take(firstFunction).Where(w=>(w[0]&65535)>=71 && (w[0]&65535)<=75));Append(b.Decorations);
        Append(records.Take(firstFunction).Where(w=>(w[0]&65535)>=19 && (w[0]&65535)<59));Append(b.Types);
        Append(records.Take(firstFunction).Where(w=>(w[0]&65535)==59));Append(b.Globals);
        Append(records.Skip(firstFunction));Append(b.Body);
        return MemoryMarshal.AsBytes(result.ToArray().AsSpan()).ToArray();
    }
}

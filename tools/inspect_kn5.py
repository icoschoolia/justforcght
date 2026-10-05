#!/usr/bin/env python3
import struct, json, re
from pathlib import Path

PARTS = [
    Path("gp_2026_mcl40.kn5.001"),
    Path("gp_2026_mcl40.kn5.002"),
    Path("gp_2026_mcl40.kn5.003"),
    Path("gp_2026_mcl40.kn5.004"),
    Path("gp_2026_mcl40.kn5.005"),
]
OUT = Path("kn5_report.json")
KN5 = Path("gp_2026_mcl40.reconstructed.kn5")

buf = b"".join(p.read_bytes() for p in PARTS)
KN5.write_bytes(buf)

class Reader:
    def __init__(self, b):
        self.b=b; self.p=0
    def u8(self):
        v=self.b[self.p]; self.p+=1; return v
    def i32(self):
        v=struct.unpack_from("<i", self.b, self.p)[0]; self.p+=4; return v
    def u32(self):
        v=struct.unpack_from("<I", self.b, self.p)[0]; self.p+=4; return v
    def f32(self):
        v=struct.unpack_from("<f", self.b, self.p)[0]; self.p+=4; return v
    def skip(self,n):
        self.p += n
        if self.p > len(self.b): raise ValueError(f"EOF at {self.p}")
    def string(self):
        n=self.u32()
        if n>1_000_000 or self.p+n>len(self.b):
            raise ValueError(f"bad string length {n} at {self.p-4}")
        s=self.b[self.p:self.p+n].decode("utf-8","replace")
        self.p += n
        return s

r=Reader(buf)
magic=buf[:6].decode("ascii","replace")
r.p=6
version=r.i32()
if version>=6:
    r.i32()

texture_count=r.u32()
for _ in range(texture_count):
    r.i32(); r.string(); r.skip(r.u32())

material_count=r.u32()
materials=[]
for _ in range(material_count):
    name=r.string(); shader=r.string()
    if version>4:
        r.u8(); r.u8(); r.i32()
    props=r.u32()
    for _ in range(props):
        r.string(); r.f32(); r.skip(36)
    slots=r.u32()
    for _ in range(slots):
        r.string(); r.u32(); r.string()
    materials.append({"name":name,"shader":shader})

nodes=[]
bounds=[float("inf")]*3, [float("-inf")]*3

def walk(depth=0,parent=None):
    start=r.p
    ntype=r.i32()
    name=r.string()
    child_count=r.i32()
    active=r.u8()
    node={"depth":depth,"type":ntype,"kind":{1:"dummy",2:"mesh",3:"skinned"}.get(ntype,"unknown"),
          "name":name,"parent":parent,"child_count":child_count,"active":active}
    if ntype==1:
        node["matrix"]=list(r.f32() for _ in range(16))
    elif ntype in (2,3):
        r.u8(); r.u8(); r.u8()
        if ntype==3:
            nb=r.u32(); bones=[]
            for _ in range(nb):
                bones.append(r.string()); r.skip(64)
            node["bones"]=bones
        vc=r.u32()
        lo=[float("inf")]*3; hi=[float("-inf")]*3
        for _ in range(vc):
            x,y,z=r.f32(),r.f32(),r.f32()
            lo[0]=min(lo[0],x); lo[1]=min(lo[1],y); lo[2]=min(lo[2],z)
            hi[0]=max(hi[0],x); hi[1]=max(hi[1],y); hi[2]=max(hi[2],z)
            r.skip(8*4)  # normal3 + uv2 + tangent3
        ic=r.u32(); r.skip(ic*2)
        mid=r.u32()
        r.skip(4+8+12+4+1)
        node["vertices"]=vc
        node["indices"]=ic
        node["material_id"]=mid
        node["material"]=materials[mid]["name"] if 0<=mid<len(materials) else ""
        node["local_bounds"]={"min":lo,"max":hi}
        # Mesh bounds are in node-local coordinates; useful for relative placement.
    else:
        raise ValueError(f"unknown node type {ntype} {name!r} at {start}")
    nodes.append(node)
    for _ in range(child_count):
        walk(depth+1,name)

walk()

keywords=re.compile(r"wheel|susp|hub|upright|steer|front|wing|nose|floor|sidepod|barge|rear|diffuser|brake|disc|tyre|tire|body|chassis|cockpit|halo|collision|collider",re.I)
interesting=[n for n in nodes if keywords.search(n["name"])]

report={
    "magic":magic,
    "version":version,
    "bytes":len(buf),
    "textures":texture_count,
    "materials":len(materials),
    "nodes":len(nodes),
    "kinds":{k:sum(1 for n in nodes if n["kind"]==k) for k in ["dummy","mesh","skinned"]},
    "material_samples":materials[:80],
    "interesting_nodes":interesting[:500],
    "node_names":[n["name"] for n in nodes],
    "parse_end":r.p,
    "remaining_bytes":len(buf)-r.p,
}
OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps({
    "magic":magic, "version":version, "bytes":len(buf),
    "textures":texture_count, "materials":len(materials), "nodes":len(nodes),
    "interesting":len(interesting), "parse_end":r.p, "remaining":len(buf)-r.p
}, indent=2))

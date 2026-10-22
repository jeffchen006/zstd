#!/usr/bin/env python3
"""Independent baseline/candidate recheck using zstd's in-memory CLI benchmark."""
import argparse
import hashlib
import json
import re
import statistics
import subprocess
import tarfile
from pathlib import Path

BASE = "49cf51799ea051457f57243527aa2058f999f005"
HERE = Path(__file__).resolve().parent

def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, **kwargs)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True, help="Local upstream Git repository containing the pinned base commit")
    p.add_argument("--corpus", type=Path, required=True, help="Extracted full 12-file Silesia directory")
    p.add_argument("--out", type=Path, required=True, help="New output directory; must not exist")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--seconds", type=int, default=2)
    p.add_argument("--rounds", type=int, default=7)
    p.add_argument("--aa-pairs", type=int, default=3)
    p.add_argument("--per-file-pairs", type=int, default=5)
    p.add_argument("--per-file-seconds", type=int, default=1)
    p.add_argument("--skip-per-file", action="store_true")
    a = p.parse_args()
    if min(a.jobs,a.seconds,a.rounds,a.aa_pairs,a.per_file_pairs,a.per_file_seconds)<1:
        p.error("counts and durations must be positive")
    source,corpus,out = a.source.resolve(),a.corpus.resolve(),a.out.resolve()
    expected=json.loads((HERE/"corpus-files.json").read_text())
    for name,meta in expected.items():
        f=corpus/name
        if not f.is_file() or f.stat().st_size!=meta["bytes"] or digest(f)!=meta["sha256"]:
            raise RuntimeError("Corpus identity mismatch: "+name)
    if digest(HERE/"c0002-r0.patch")!="2872be44821edd6393bbd2646a167432fd8a234759cfaadd13a971dede8194a9":
        raise RuntimeError("Patch identity mismatch")
    run(["git","cat-file","-e",BASE+"^{commit}"],cwd=source)
    out.mkdir(parents=True,exist_ok=False)
    combined=out/"silesia-all"
    with combined.open("wb") as f:
        for name in sorted(expected):f.write((corpus/name).read_bytes())
    archive=out/"source.tar"
    with archive.open("wb") as f:run(["git","archive",BASE],cwd=source,stdout=f)
    build_commands={}
    for label in ["baseline","candidate"]:
        directory=out/label;directory.mkdir()
        with tarfile.open(archive) as t:t.extractall(directory)
        run(["git","init","-q"],cwd=directory)
        if label=="candidate":run(["git","apply",str(HERE/"c0002-r0.patch")],cwd=directory)
        command=["make",f"-j{a.jobs}","zstd","CC=cc","CFLAGS=-O3","DEBUGLEVEL=0","HAVE_ZLIB=0","HAVE_LZMA=0","HAVE_LZ4=0"]
        build_commands[label]=command
        with (out/(label+"-build.log")).open("w") as f:run(command,cwd=directory,stdout=f,stderr=subprocess.STDOUT)
    meta={"base":BASE,"compiler":subprocess.check_output(["cc","--version"],text=True),"commands":build_commands,
          "binary_sha256":{label:digest(out/label/"zstd") for label in build_commands},
          "corpus_files":expected,"combined_sha256":digest(combined),
          "method":"Two-binary alternating AB/BA recheck; the saved original aggregate matrix used a balanced three-binary schedule."}
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    original=combined.read_bytes()
    verified=[]
    for level in [1,3,6,9]:
        baseline_frame=None
        for label in ["baseline","candidate"]:
            exe=str(out/label/"zstd")
            frame=subprocess.check_output([exe,"--single-thread","-q",f"-{level}","-c",str(combined)])
            if baseline_frame is None:baseline_frame=frame
            if frame!=baseline_frame:raise RuntimeError("Compressed output differs")
            if subprocess.check_output([exe,"-q","-d","-c"],input=frame)!=original:
                raise RuntimeError("Round-trip mismatch")
            verified.append({"level":level,"label":label,"compressed_bytes":len(frame),"frame_sha256":hashlib.sha256(frame).hexdigest()})
    del original
    (out/"correctness.json").write_text(json.dumps(verified,indent=2)+"\n")
    samples=[]
    def bench(label,level,data,seconds,case,round_id,slot):
        cmd=[str(out/label/"zstd"),"-q",f"-b{level}",f"-i{seconds}",str(data)]
        proc=run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        m=re.findall(r"^-?(\d+)\s+(\d+)\s+\(([\d.]+)\)\s+([\d.]+)\s+MB/s\s+([\d.]+)\s+MB/s",proc.stdout,re.M)
        if len(m)!=1 or int(m[0][0])!=level:raise RuntimeError((proc.stdout,proc.stderr))
        x=m[0];record={"case":case,"level":level,"round":round_id,"slot":slot,"label":label,"command":cmd,"stdout":proc.stdout,"stderr":proc.stderr,"compressed_bytes":int(x[1]),"ratio":float(x[2]),"compression_mbps":float(x[3]),"decompression_mbps":float(x[4])}
        samples.append(record)
        with (out/"samples.jsonl").open("a") as f:f.write(json.dumps(record)+"\n")
    for level in [1,3,6,9]:
        for i in range(a.aa_pairs):
            for slot in [0,1]:bench("baseline",level,combined,a.seconds,f"AA-L{level}",i,slot)
    for i in range(a.rounds):
        for level in ([1,3,6,9] if i%2==0 else [9,6,3,1]):
            for label in (["baseline","candidate"] if i%2==0 else ["candidate","baseline"]):
                bench(label,level,combined,a.seconds,f"all-L{level}",i,label)
        print("Aggregate round",i+1,"complete",flush=True)
    if not a.skip_per_file:
        for name in sorted(expected):
            for level in [6,9]:
                for i in range(a.per_file_pairs):
                    for label in (["baseline","candidate"] if i%2==0 else ["candidate","baseline"]):
                        bench(label,level,corpus/name,a.per_file_seconds,name+f"-L{level}",i,label)
            print("Per-file",name,"complete",flush=True)
    summary=[]
    for case in sorted({x["case"] for x in samples}):
        group=[x for x in samples if x["case"]==case]
        if case.startswith("AA-"):
            left=[x for x in group if x["slot"]==0];right=[x for x in group if x["slot"]==1]
        else:
            left=[x for x in group if x["label"]=="baseline"];right=[x for x in group if x["label"]=="candidate"]
        assert len(left)==len(right) and len({x["compressed_bytes"] for x in left+right})==1
        for metric in ["compression_mbps","decompression_mbps"]:
            ratios=[b[metric]/a[metric] for a,b in zip(left,right)]
            summary.append({"case":case,"metric":metric,"pairs":len(ratios),"baseline_median_mbps":statistics.median(x[metric] for x in left),"candidate_median_mbps":statistics.median(x[metric] for x in right),"median_paired_change_pct":100*(statistics.median(ratios)-1),"pair_range_pct":[100*(min(ratios)-1),100*(max(ratios)-1)]})
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("Saved results:",out)

if __name__=="__main__":main()

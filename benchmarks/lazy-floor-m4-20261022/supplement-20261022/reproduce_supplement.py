#!/usr/bin/env python3
"""Recheck the supplemental lazy-floor matrix with separately built binaries.

Build commands and exact revisions are recorded in the evidence. Run on a quiet
machine; this portable helper does not suspend jobs or change host settings.
"""
from pathlib import Path
import argparse,subprocess,random,json,time,re,hashlib,statistics,os
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
 p.add_argument('--silesia',type=Path,required=True,help='Extracted original 12-file corpus')
 p.add_argument('--enwik8',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--baseline-fullbench',type=Path);p.add_argument('--candidate-fullbench',type=Path)
 p.add_argument('--corpus-manifest',type=Path,default=Path(__file__).resolve().parent.parent/'corpus-files.json')
 p.add_argument('--with-raw-dictionary',action='store_true',help='Also test64KiB prefix dictionaries and32KiB chunks')
 p.add_argument('--cpu',type=int,help='Linux process affinity only, using taskset')
 p.add_argument('--rounds',type=int,default=3);p.add_argument('--seconds',type=int,default=2)
 p.add_argument('--case',help='Run one named case for a bounded smoke check; omitted for the full matrix')
 p.add_argument('--skip-aa',action='store_true',help='Skip same-binary controls for smoke checks only')
 a=p.parse_args();assert a.rounds>0 and a.seconds>0
 a.out.mkdir(parents=True,exist_ok=False)
 old,new=a.baseline.resolve(),a.candidate.resolve();data=a.out/'data';data.mkdir()
 combined=data/'silesia-all'
 names=sorted(f for f in a.silesia.iterdir() if f.is_file())
 assert len(names)==12 and sum(f.stat().st_size for f in names)==211938580
 expected=json.loads(a.corpus_manifest.read_text())
 for f in names:assert f.stat().st_size==expected[f.name]['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==expected[f.name]['sha256'],f
 env=dict(os.environ)
 for name in ['ZSTD_NBTHREADS','ZSTD_CLEVEL']:env.pop(name,None)
 (a.out/'binaries.json').write_text(json.dumps({label:{'path':str(exe),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest()} for label,exe in [('baseline',old),('candidate',new)]},indent=2)+'\n')
 with combined.open('wb') as f:
  for name in names:f.write(name.read_bytes())
 text=a.enwik8.read_bytes();assert len(text)==100000000 and hashlib.md5(text).hexdigest()=='a1fa5ffddb56f4953e226637dabbb36a'
 random_data=random.Random(221022).randbytes(16*1024*1024)
 (data/'random16MiB').write_bytes(random_data)
 (data/'random-then-text16MiB').write_bytes(random_data[:8*1024*1024]+text[:8*1024*1024])
 cases=[]
 for name,path in [('silesia',combined),('enwik8',a.enwik8.resolve()),('random16MiB',data/'random16MiB')]:
  for level in [5,6,7,9,12,13]:cases.append((name+f'-L{level}',path,level,[],a.rounds,a.seconds))
 for level in [6,9]:
  cases.extend([(f'silesia-hashchain-L{level}',combined,level,['--no-row-match-finder'],a.rounds,a.seconds),(f'silesia-32KiB-L{level}',combined,level,['-B32K'],a.rounds,a.seconds),(f'mixed-L{level}',data/'random-then-text16MiB',level,[],a.rounds,a.seconds)])
 for name in ['x-ray','sao','osdb']:cases.append((f'confirm-{name}-L6',(a.silesia/name).resolve(),6,[],5,5))
 if a.with_raw_dictionary:
  for name in ['dickens','xml']:
   content=(a.silesia/name).read_bytes();dp=data/f'{name}-dict64KiB';ip=data/f'{name}-after-dict4MiB';dp.write_bytes(content[:65536]);ip.write_bytes(content[65536:65536+4*1024*1024])
   for level in [6,9]:
    frames=[]
    for exe in [old,new]:
     r=subprocess.run([str(exe),'-q',f'-{level}','--single-thread','--no-asyncio','-D',str(dp),'-c',str(ip)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env);assert r.returncode==0,r.stderr
     d=subprocess.run([str(exe),'-qdc','-D',str(dp)],input=r.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env);assert d.returncode==0 and d.stdout==ip.read_bytes();frames.append(r.stdout)
    assert frames[0]==frames[1]
    cases.append((f'rawdict-{name}-L{level}',ip,level,['-B32K','-D',str(dp)],a.rounds,a.seconds))
 random.Random(221023).shuffle(cases)
 if a.case:
  cases=[c for c in cases if c[0]==a.case]
  assert cases,'Unknown case'
 prefix=['taskset','-c',str(a.cpu)] if a.cpu is not None else []
 all_samples=[]
 def save(r):
  all_samples.append(r)
  with (a.out/'samples.jsonl').open('a') as f:f.write(json.dumps(r)+'\n')
 def cli(case,path,level,flags,round_id,slot,label,seconds):
  cmd=prefix+[str(old if label=='baseline' else new),'-q',f'-b{level}',f'-i{seconds}']+flags+[str(path)]
  start=time.time();r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
  m=re.findall(r'^-?(\d+)\s+(\d+)\s+\(([\d.]+)\)\s+([\d.]+)\s+MB/s\s+([\d.]+)\s+MB/s',r.stdout,re.M)
  assert r.returncode==0 and len(m)==1,(cmd,r.stdout,r.stderr)
  l,size,ratio,c,d=m[0]
  save({'case':case,'round':round_id,'slot':slot,'label':label,'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'started':start,'elapsed_seconds':time.time()-start,'compressed_bytes':int(size),'compression_mbps':float(c),'decompression_mbps':float(d)})
 if not a.skip_aa:
  for i in range(3):
   for slot in [0,1]:cli('AA-silesia-L9',combined,9,[],i,slot,'baseline',3)
 for name,path,level,flags,rounds,seconds in cases:
  for i in range(rounds):
   for slot,label in enumerate(['baseline','candidate'] if i%2==0 else ['candidate','baseline']):cli(name,path,level,flags,i,slot,label,seconds)
  print(name,'complete',flush=True)
 if a.baseline_fullbench and a.candidate_fullbench:
  for n in [1024,32768]:
   inp=data/f'enwik8-first-{n}';inp.write_bytes(text[:n])
   for level in [6,9]:
    for i in range(3):
     for slot,label in enumerate(['baseline','candidate'] if i%2==0 else ['candidate','baseline']):
      exe=a.baseline_fullbench if label=='baseline' else a.candidate_fullbench
      cmd=prefix+[str(exe.resolve()),'-b7',f'-l{level}','-i3',str(inp)]
      r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
      assert r.returncode==0 and 'validation failed' not in r.stdout+r.stderr and 'compressStream' in r.stdout+r.stderr and re.search(r':\s*[\d.]+\s*MB/s',r.stdout+r.stderr),(cmd,r.stdout,r.stderr)
      with (a.out/'streaming.jsonl').open('a') as f:f.write(json.dumps({'bytes':n,'level':level,'round':i,'slot':slot,'label':label,'command':cmd,'stdout':r.stdout,'stderr':r.stderr,'returncode':r.returncode})+'\n')
 summary=[]
 for case in sorted({r['case'] for r in all_samples}):
  group=[r for r in all_samples if r['case']==case];ratios=[]
  for i in sorted({r['round'] for r in group}):
   pair=sorted([r for r in group if r['round']==i],key=lambda r:r['slot'] if case.startswith('AA-') else r['label'])
   b,c=pair;assert b['compressed_bytes']==c['compressed_bytes'];ratios.append(c['compression_mbps']/b['compression_mbps'])
  summary.append({'case':case,'pairs':len(ratios),'compression_change_pct':100*(statistics.median(ratios)-1),'pair_ratios':ratios})
 (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 (a.out/'inputs.json').write_text(json.dumps({str(f):{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in names+list(data.iterdir())+[a.enwik8]},indent=2)+'\n')
if __name__=='__main__':main()

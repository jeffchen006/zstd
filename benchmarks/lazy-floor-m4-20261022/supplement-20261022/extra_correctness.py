from pathlib import Path
import json,subprocess,hashlib,random,time
P=Path(__file__).resolve().parent
builds=json.loads((P/'builds.json').read_text())
by={(b['compiler_label'],b['label']):b['binary'] for b in builds}
samples={}
for n in [0,1,3,4,7,8,9,15,16,31,32,63,64,127,128,255,256,1023,1024,32767,32768,131071,131072,131073]:
 base=b'0123456789abcdef the quick brown fox\n'
 samples[f'repeat-{n}']=(base*(n//len(base)+1))[:n]
for n in [64,127,128,1024,32768]:samples[f'random-{n}']=random.Random(n).randbytes(n)
records=[]
start=time.time()
for comp in sorted({b['compiler_label'] for b in builds}):
 for name,data in samples.items():
  for l in [5,6,7,9,12,13]:
   for row in ['--row-match-finder','--no-row-match-finder']:
    outputs=[]
    for label in ['baseline','candidate']:
     cmd=[by[comp,label],'-q','-c',f'-{l}',row]
     r=subprocess.run(cmd,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE);assert r.returncode==0,(cmd,r.stderr)
     d=subprocess.run([by[comp,label],'-qdc'],input=r.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE);assert d.returncode==0 and d.stdout==data,(name,comp,l,row,label)
     outputs.append(r.stdout)
    assert outputs[0]==outputs[1],(name,comp,l,row)
    records.append({'compiler':comp,'sample':name,'input_bytes':len(data),'input_sha256':hashlib.sha256(data).hexdigest(),'level':l,'row_mode':row,'compressed_bytes':len(outputs[0]),'compressed_sha256':hashlib.sha256(outputs[0]).hexdigest(),'byte_identical':True,'roundtrip':True})
(P/'extra-correctness.json').write_text(json.dumps({'records':records,'count':len(records),'elapsed_seconds':time.time()-start,'description':'Both compiler builds; match floor/tail boundaries, repetitive and random inputs; row/hashchain modes; byte equivalence and round trips.'},indent=2)+'\n')
print(len(records),'boundary configurations passed',flush=True)

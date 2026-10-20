"""Immutable per-part Git trees keep each CDN package below its package-size limit."""
import hashlib,os,re,subprocess
from pathlib import Path

def create_parts(apk,work,tag):
 if not re.fullmatch(r'qvk-public[0-9]+',tag):raise ValueError('QVK tag required')
 work=Path(work);work.mkdir(parents=True,exist_ok=True)
 subprocess.run(['git','init','-q',str(work)],check=True)
 def git(*args,body=None,env=None):return subprocess.check_output(['git','-c','user.name=QVK release automation','-c','user.email=qvk-release@users.noreply.github.com',*args],cwd=work,input=body,env=env).decode().strip()
 dates={**os.environ,'GIT_AUTHOR_DATE':'2000-01-01T00:00:00Z','GIT_COMMITTER_DATE':'2000-01-01T00:00:00Z'}
 parts=[];tags=[];temp=work/'chunk.bin'
 with Path(apk).open('rb') as stream:
  while chunk:=stream.read(8*1024*1024):
   n=len(parts);name=f'apk.part{n:03}';temp.write_bytes(chunk)
   blob=git('hash-object','-w',str(temp.resolve()))
   distribution=git('mktree',body=f'100644 blob {blob}\t{name}\n'.encode())
   qvk=git('mktree',body=f'040000 tree {distribution}\tdistribution\n'.encode())
   tree=git('mktree',body=f'040000 tree {qvk}\tqvk\n'.encode())
   commit=git('commit-tree',tree,'-m',f'{tag} signed APK part {n}',env=dates)
   ref=f'refs/tags/qvk-cdn-{tag.removeprefix("qvk-")}-part{n:03}'
   git('update-ref',ref,commit);tags.append(ref)
   parts.append(dict(name=name,bytes=len(chunk),sha256=hashlib.sha256(chunk).hexdigest(),commit=commit))
 temp.unlink(missing_ok=True)
 if not 0<len(parts)<=64:raise ValueError('Distribution size limit')
 return parts,tags

def publish(apk,work,repo,tag):
 if repo!='3Be3ga4Ka/vk-lite-updates':raise ValueError('Wrong distribution repository')
 parts,tags=create_parts(apk,work,tag)
 subprocess.run(['git','-c','credential.helper=!gh auth git-credential','push','--atomic','https://github.com/'+repo+'.git',*tags],cwd=work,check=True)
 return {'schema':1,'parts':parts}

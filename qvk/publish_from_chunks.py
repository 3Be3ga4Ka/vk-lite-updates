"""GitHub runner upload path when an external CLI identity cannot use uploads.github.com."""
import hashlib,json,os,re,subprocess,tempfile,urllib.request,urllib.parse,zipfile
from pathlib import Path
from publish_channel import activate,gh

def main():
 repo=os.environ['QVK_REPOSITORY'];ref=os.environ['QVK_STAGING_REF']
 if repo!='3Be3ga4Ka/vk-lite-updates' or not re.fullmatch(r'qvk-upload-public[0-9]+',ref):raise ValueError('Wrong release staging branch')
 root=Path('qvk/incoming');data=json.loads((root/'manifest.json').read_text());item=data['update'];tag=data['tag'];name=item['apk_url'].rsplit('/',1)[-1]
 if tag!=ref.replace('qvk-upload-','qvk-') or not re.fullmatch(r'QVK_[A-Za-z0-9_.-]+\.apk',name):raise ValueError('Wrong release tag or filename')
 if item['package']!='ru.qmods.qvk' or item['apk_url']!=f'https://github.com/{repo}/releases/download/{tag}/{name}':raise ValueError('Wrong QVK channel')
 if not 0<item['apk_size']<=536870912 or not 0<len(data['chunks'])<=16:raise ValueError('Release size limit')
 with tempfile.TemporaryDirectory() as td:
  apk=Path(td)/name;digest=hashlib.sha256();size=0
  with apk.open('wb') as out:
   for n,entry in enumerate(data['chunks']):
    if entry['name']!=f'apk.part{n:03}' or not 0<entry['bytes']<=40*1024*1024:raise ValueError('Chunk metadata')
    chunk=(root/entry['name']).read_bytes()
    if len(chunk)!=entry['bytes'] or hashlib.sha256(chunk).hexdigest()!=entry['sha256']:raise ValueError('Chunk checksum mismatch')
    out.write(chunk);digest.update(chunk);size+=len(chunk)
  if size!=item['apk_size'] or digest.hexdigest()!=item['sha256']:raise ValueError('APK checksum mismatch')
  sdk=Path(os.environ.get('ANDROID_HOME',os.environ.get('ANDROID_SDK_ROOT','/usr/local/lib/android/sdk')))
  signer=sorted((sdk/'build-tools').glob('*/apksigner'))[-1]
  verified=subprocess.check_output([str(signer),'verify','--verbose','--print-certs',str(apk)],text=True)
  cert='a40da80a59d170caa950cf15c18c454d47a39b26989d8b640ecd745ba71bf5dc'
  if set(re.findall(r'certificate sha-256 digest:\s*([0-9a-fA-F]{64})', verified.lower())) != {cert}:raise ValueError('Wrong signer: ' + repr(re.findall(r'certificate[^\n]*', verified)))
  metadata=subprocess.check_output([str(signer.parent/'aapt'),'dump','badging',str(apk)],text=True).splitlines()[0]
  for attribute,value in [('name','ru.qmods.qvk'),('versionCode',str(item['version_code'])),('versionName',item['version_name'])]:
   if f"{attribute}='{value}'" not in metadata:raise ValueError('APK metadata mismatch')
  sources=Path(td)/('QVK_'+tag.removeprefix('qvk-')+'_sources.zip')
  with zipfile.ZipFile(apk) as archive:sources.write_bytes(archive.read('assets/third_party/sova-port10-helper-sources.zip'))
  with zipfile.ZipFile(sources) as archive:
   if archive.testzip() or 'build_public'+tag.removeprefix('qvk-public')+'.py' not in archive.namelist():raise ValueError('Source bundle mismatch')
  extras=[]
  with zipfile.ZipFile(sources) as archive:
   for entry in archive.infolist():
    if not re.fullmatch(r'output/QVK_server_[0-9]+\.[0-9]+_UPDATE\.zip',entry.filename):continue
    if not 0<entry.file_size<=20*1024*1024:raise ValueError('Server update size limit')
    extra=Path(td)/Path(entry.filename).name;extra.write_bytes(archive.read(entry))
    with zipfile.ZipFile(extra) as server:
     if server.testzip() or 'qvk-community.php' not in server.namelist() or 'qvk-community-config.php' in server.namelist():raise ValueError('Server update bundle mismatch')
    extras.append(extra)
  manifest=Path(td)/'qvk-update.json';manifest.write_text(json.dumps(item,ensure_ascii=False,indent=2)+'\n')
  release_id=data['release_id']
  if not isinstance(release_id,int) or release_id<=0:raise ValueError('Invalid release ID')
  release=json.loads(gh('api',f'repos/{repo}/releases/{release_id}'))
  if release['tag_name']!=tag:raise ValueError('Release tag mismatch')
  if release['draft']:
   for asset in release['assets']:
    if asset['name'] in [name,'qvk-update.json',sources.name]+[extra.name for extra in extras]:
     subprocess.run(['gh','api','--method','DELETE',f"repos/{repo}/releases/assets/{asset['id']}",'--silent'],check=True)
   endpoint=release['upload_url'].split('{',1)[0]
   if endpoint!=f'https://uploads.github.com/repos/{repo}/releases/{release_id}/assets':raise ValueError('Invalid upload endpoint')
   for file,mime in [(apk,'application/vnd.android.package-archive'),(manifest,'application/json'),(sources,'application/zip')]+[(extra,'application/zip') for extra in extras]:
    request=urllib.request.Request(endpoint+'?name='+urllib.parse.quote(file.name),data=file.read_bytes(),method='POST',headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Content-Type':mime,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    with urllib.request.urlopen(request,timeout=300) as uploaded:
     if uploaded.status!=201:raise RuntimeError('Asset upload failed')
     result=json.load(uploaded)
     if result['name']!=file.name or result['size']!=file.stat().st_size:raise ValueError('Uploaded asset mismatch')
   subprocess.run(['gh','api','--method','PATCH',f'repos/{repo}/releases/{release_id}','-F','draft=false','-f','make_latest=false','--silent'],check=True)
  # GITHUB_TOKEN release events do not start another workflow; activate explicitly here.
  activate(repo,tag)
  subprocess.run(['gh','api','--method','DELETE',f'repos/{repo}/git/refs/heads/{ref}','--silent'],check=True)
  print('Published, broadcast activated, temporary upload branch removed')
if __name__=='__main__':main()

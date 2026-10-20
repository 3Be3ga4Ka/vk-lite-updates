"""Replicate only public catalog pages; never credentials, entitlement grants or private requests."""
import json,time,urllib.request
from pathlib import Path

def fetch(kind,offset):
 url=f'https://qmods.ru/qvk-community.php?action=list&kind={kind}&sort=new&offset={offset}'
 with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'QVK public catalog mirror'}),timeout=30) as response:
  data=response.read(262145)
  if len(data)>262144:raise ValueError('Catalog page too large')
  page=json.loads(data)
  if page.get('schema')!=1:raise ValueError('Catalog schema')
  return page

def main():
 root=Path('qvk/catalog');root.mkdir(exist_ok=True,parents=True)
 for kind in ['theme','settings']:
  rows=[];offset=0
  for _ in range(25):
   page=fetch(kind,offset);candidate=rows+page['items']
   if len(json.dumps(candidate,ensure_ascii=False).encode())>900000:break
   rows=candidate;offset=page['next']
   if offset<0:break
  value={'schema':1,'mirrored_at':int(time.time()),'source':'https://qmods.ru/qvk-community.php','items':rows,'total':page['total']}
  (root/(kind+'.json')).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n')
if __name__=='__main__':main()

"""Public bootstrap: downloads release assets only; never clones the development repository."""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import struct
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import webbrowser
from zipfile import ZipFile

TAG=re.compile(r'v(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})')
SHA=re.compile('[a-f0-9]{64}')
ASSET='CodeRoute-win-py313.zip'
LIMIT=64*1024*1024


def write(path,value):
    temp=path.with_suffix('.'+secrets.token_hex(8)+'.tmp')
    try:
        temp.write_text(json.dumps(value),encoding='utf-8');os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)


def safe_name(name):
    parts=PurePosixPath(name).parts
    bad={'con','prn','aux','nul',*[f'com{i}' for i in range(1,10)],*[f'lpt{i}' for i in range(1,10)]}
    if (not parts or '/'.join(parts)!=name or name.startswith('/') or '\\' in name or
        any(part in {'.','..'} or part.endswith((' ','.')) or re.search(r'[\x00-\x1f:<>"|?*]',part) or
            part.split('.')[0].lower() in bad or part.lower() in ['artifacts','.venv','.git','__pycache__'] or
            part.lower().startswith('.env') for part in parts) or
        name.lower().endswith(('.sqlite3','.crrecords','.key','.pem','.pfx','.p12'))):return False
    return (name in ['manage.pyc','requirements.txt','THIRD_PARTY.md'] or
            (parts[0] in ['catalog','config'] and name.endswith(('.pyc','.json'))) or parts[0] in ['frontend','judge'])


def unpack(archive,folder,expected,tag):
    if archive.stat().st_size>LIMIT or not TAG.fullmatch(tag) or not SHA.fullmatch(expected) or hashlib.sha256(archive.read_bytes()).hexdigest()!=expected:
        raise ValueError('배포 패키지 체크섬·버전이 일치하지 않습니다.')
    if folder.resolve()!=folder:raise ValueError('설치 경로가 바뀌었습니다.')
    with ZipFile(archive) as bundle:
        entries=bundle.infolist();names=[entry.filename for entry in entries]
        if len(names)>10000 or len(set(n.casefold() for n in names))!=len(names) or sum(e.file_size for e in entries)>LIMIT:
            raise ValueError('배포 패키지 경로·크기 제한을 넘었습니다.')
        if 'package.json' not in names:raise ValueError('배포 파일 목록이 없습니다.')
        if bundle.getinfo('package.json').file_size>1_000_000:raise ValueError('배포 파일 목록이 너무 큽니다.')
        manifest=json.loads(bundle.read('package.json'))
        files=manifest.get('files') if isinstance(manifest,dict) else None
        if (not isinstance(files,dict) or not files or manifest.get('format')!=1 or manifest.get('version')!=tag or
            manifest.get('python_magic')!=importlib.util.MAGIC_NUMBER.hex() or set(names)!={*files,'package.json'} or
            not {'manage.pyc','requirements.txt','config/settings.pyc','catalog/apps.pyc'}<=files.keys()):
            raise ValueError('지원하는 실행 패키지가 아닙니다.')
        for entry in entries:
            name=entry.filename;mode=(entry.external_attr>>16)&0o170000
            if entry.is_dir() or mode not in [0,0o100000] or (name!='package.json' and not safe_name(name)):
                raise ValueError('안전하지 않은 배포 경로·링크입니다.')
            raw=bundle.read(name)
            if name!='package.json' and (not isinstance(files[name],str) or not SHA.fullmatch(files[name]) or hashlib.sha256(raw).hexdigest()!=files[name]):
                raise ValueError('배포 파일 검증에 실패했습니다.')
            if name.endswith('.pyc') and raw[:4]!=importlib.util.MAGIC_NUMBER:raise ValueError('Python 버전이 맞지 않습니다.')
        if folder.exists():
            if set(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file())!=set(names):raise ValueError('기존 버전 폴더의 파일 구성이 바뀌었습니다.')
            if any((folder/name).resolve()!=folder/name or (folder/name).read_bytes()!=bundle.read(name) for name in names):raise ValueError('기존 버전 파일이 바뀌었습니다.')
            return manifest
        folder.mkdir(parents=True)
        for name in names:
            target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(bundle.read(name))
    return manifest


class Redirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        url=urlsplit(newurl)
        if url.scheme!='https' or url.hostname not in ['github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'] or url.port not in [None,443] or url.username or url.password:
            raise ValueError('허용하지 않은 배포 이동 주소입니다.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def read_url(url,limit):
    request=Request(url,headers={'User-Agent':'CodeRoute-launcher','Accept':'application/vnd.github+json' if 'api.github.com/' in url else 'application/octet-stream'})
    with build_opener(Redirects).open(request,timeout=15) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('배포 다운로드 크기 제한을 넘었습니다.')
    return data


def release(repository):
    if not isinstance(repository,str) or not re.fullmatch(r'dang0321/[A-Za-z0-9_.-]+',repository):
        raise ValueError('공개 실행 전용 저장소 주소가 아직 확정되지 않았습니다.')
    if repository.lower()=='dang0321/coderoute':raise ValueError('원본 개발 저장소를 배포 주소로 사용하지 않습니다.')
    value=json.loads(read_url('https://api.github.com/repos/'+repository+'/releases/latest',1_000_000))
    tag=value.get('tag_name') if isinstance(value,dict) else None
    if not isinstance(tag,str) or not TAG.fullmatch(tag) or value.get('draft') is not False or value.get('prerelease') is not False:
        raise ValueError('정식 배포 정보가 아닙니다.')
    if value.get('html_url')!='https://github.com/'+repository+'/releases/tag/'+tag:raise ValueError('다른 저장소의 배포 정보입니다.')
    assets=value.get('assets'); assets=assets if isinstance(assets,list) else []
    assets=[item for item in assets if isinstance(item,dict) and item.get('name')==ASSET]
    if len(assets)!=1:raise ValueError('Windows 실행 패키지를 찾지 못했습니다.')
    asset=assets[0];digest=asset.get('digest','')
    if (not isinstance(digest,str) or not digest.startswith('sha256:') or not SHA.fullmatch(digest[7:]) or
        type(asset.get('size')) is not int or not 0<asset['size']<=LIMIT or asset.get('state')!='uploaded' or
        asset.get('browser_download_url')!='https://github.com/'+repository+'/releases/download/'+tag+'/'+ASSET):
        raise ValueError('배포 파일의 주소·체크섬을 확인하지 못했습니다.')
    return tag,asset


@contextmanager
def lock(state):
    import msvcrt
    state.mkdir(parents=True,exist_ok=True)
    if state.resolve()!=state:raise ValueError('실행 데이터 폴더가 다른 경로를 가리킵니다.')
    with (state/'launcher.lock').open('a+b') as stream:
        stream.write(b'0');stream.flush();stream.seek(0)
        try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise ValueError('다른 코드루트 시작·종료 작업이 진행 중입니다.') from None
        try:yield
        finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)


def current(state):
    path=state/'current.json'
    if not path.exists():return None
    value=json.loads(path.read_text(encoding='utf-8'));name=value.get('directory') if isinstance(value,dict) else None
    if not isinstance(name,str) or not re.fullmatch(r'v\d+\.\d+\.\d+-[a-f0-9]{16}',name):raise ValueError('현재 버전 기록을 확인해 주세요.')
    directory=state/'releases'/name
    if directory.resolve()!=directory or not (directory/'package.json').is_file():raise ValueError('현재 버전 폴더가 없습니다.')
    return directory


def manage(state,directory,*args,capture=False):
    home=state/'home';home.mkdir(exist_ok=True)
    if home.resolve()!=home:raise ValueError('학습 기록 경로가 바뀌었습니다.')
    secret=home/'artifacts/local-secret.key';secret.parent.mkdir(exist_ok=True)
    if secret.resolve()!=secret:raise ValueError('로컬 비밀키 경로가 바뀌었습니다.')
    if not secret.exists():
        with secret.open('x',encoding='ascii') as stream:stream.write(secrets.token_urlsafe(48))
    environment={**os.environ,'CODEROUTE_HOME':str(home),'DJANGO_SECRET_KEY':secret.read_text(encoding='ascii').strip(),
                 'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8'}
    result=subprocess.run([str(home/'.venv/Scripts/python.exe'),str(directory/'manage.pyc'),*args],cwd=directory,env=environment,
        capture_output=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=600)
    if result.returncode:
        (home/'artifacts/package-command-error.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        raise ValueError('실행 준비에 실패했습니다. .coderoute/home/artifacts/package-command-error.log를 확인해 주세요.')
    if not capture and result.stdout:print(result.stdout,end='')
    return result.stdout if capture else None


def install(state,archive,digest,tag):
    directory=state/'releases'/(tag+'-'+digest[:16]);old=current(state)
    if old==directory:return old
    unpack(archive,directory,digest,tag)
    home=state/'home';home.mkdir(exist_ok=True);python=home/'.venv/Scripts/python.exe'
    if old and (old/'requirements.txt').read_bytes()!=(directory/'requirements.txt').read_bytes():
        raise ValueError('필요 패키지가 변경된 배포는 별도 업그레이드 안내가 필요합니다.')
    if not python.exists():
        subprocess.run([sys.executable,'-m','venv',str(home/'.venv')],check=True,timeout=120)
    if not old:
        subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(directory/'requirements.txt')],check=True,timeout=300)
    manage(state,old or directory,'package_state','activate','--candidate='+str(directory))
    return current(state)


def run(root,action,settings='config.settings',no_browser=False):
    if sys.platform!='win32' or sys.version_info[:2]!=(3,13) or struct.calcsize('P')!=8:
        raise ValueError('현재 실행 패키지는 Windows Python 3.13 64비트용입니다.')
    state=root/'.coderoute'
    with lock(state):
        old=current(state)
        journal=state/'home/artifacts/runtime/package-journal.json'
        if journal.exists():
            if not old:raise ValueError('첫 설치 복구 기록을 수동 확인해 주세요.')
            manage(state,old,'package_state','recover');old=current(state)
        if action=='start':
            stamp=state/'update-check.json';saved=json.loads(stamp.read_text()) if stamp.exists() else {}
            if not old or time.time()-float(saved.get('at',0))>=86400:
                try:
                    config=json.loads((root/'launcher.json').read_text(encoding='utf-8'))
                    tag,asset=release(config.get('repository'))
                    oldtag=json.loads((old/'package.json').read_text())['version'] if old else 'v0.0.0'
                    version=lambda t:tuple(map(int,TAG.fullmatch(t).groups()))
                    if version(tag)>version(oldtag):
                        raw=read_url(asset['browser_download_url'],LIMIT)
                        if len(raw)!=asset['size']:raise ValueError('배포 파일 크기가 일치하지 않습니다.')
                        archive=state/'download.zip'
                        if archive.resolve()!=archive:raise ValueError('패키지 다운로드 경로가 바뀌었습니다.')
                        archive.write_bytes(raw)
                        old=install(state,archive,asset['digest'][7:],tag)
                    write(stamp,{'at':time.time()})
                except Exception:
                    if not old or journal.exists():raise
                    print('업데이트를 적용하지 못해 기존 버전으로 시작합니다. 기록과 설치 폴더는 유지했습니다.')
            manage(state,old,'prepare_local','--settings='+settings)
        if not old:raise ValueError('아직 설치된 코드루트 버전이 없습니다.')
        result=json.loads(manage(state,old,'runtime',action,'--settings='+settings,capture=True))
        print(json.dumps(result,ensure_ascii=False))
        if action=='start' and result.get('ready') and not no_browser:webbrowser.open(result['url'])
        if action=='start' and not result.get('ready'):raise ValueError('웹·채점·메일 준비 상태를 확인해 주세요.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['start','stop','status'])
    parser.add_argument('--settings',choices=['config.settings','config.qa'],default='config.settings');parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    try:run(Path(__file__).resolve().parent,args.action,args.settings,args.no_browser)
    except ValueError as error:
        print('코드루트 안내: '+str(error),file=sys.stderr);sys.exit(1)
    except Exception:
        print('코드루트 준비·갱신을 완료하지 못했습니다. .coderoute 폴더와 기록을 보관하고 실행 안내를 확인해 주세요.',file=sys.stderr);sys.exit(1)

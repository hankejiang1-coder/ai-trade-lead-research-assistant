"""Double-click launcher; keeps dependencies and the service on this computer."""
from pathlib import Path
import os,subprocess,sys,threading,webbrowser,urllib.request,json,time

ROOT=Path(__file__).resolve().parent

def main():
    if sys.version_info<(3,10):raise RuntimeError('请先安装 Python 3.10 或更新版本。')
    port=int(os.environ.get('TRADE_APP_PORT','8767'));url='http://127.0.0.1:'+str(port)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url+'/status',timeout=1) as response:running=json.load(response)
    except Exception:running=None
    if running:
        if running.get('version')=='0.4.0' and running.get('credential_settings'):
            webbrowser.open(url);return 0
        raise RuntimeError('旧版助手仍在运行。请在原运行窗口按 Control+C 停止它，再双击本启动文件。')
    interpreter=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not interpreter.exists():
        print('首次启动：创建本项目的 Python 环境，不修改系统 Python。',flush=True)
        subprocess.run([sys.executable,'-m','venv',str(ROOT/'.venv')],check=True)
    dependency=subprocess.run([str(interpreter),'-c',"import keyring; from zoneinfo import ZoneInfo; ZoneInfo('Asia/Shanghai')"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if dependency.returncode:
        print('首次启动：从 Python 软件源安装凭据库和时区支持。密钥不会保存在项目文件中。',flush=True)
        installed=subprocess.run([str(interpreter),'-m','pip','install','-r',str(ROOT/'requirements.txt')])
        if installed.returncode: print('依赖安装未成功，将以仅本次使用密钥的模式启动。',flush=True)
    timezone_ready=subprocess.run([str(interpreter),'-c',"from zoneinfo import ZoneInfo; ZoneInfo('Asia/Shanghai')"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if timezone_ready.returncode:
        raise RuntimeError('时区数据不可用，请确认网络并重新启动以完成 requirements.txt 依赖安装。')
    def open_when_ready():
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(30):
            try:
                with opener.open(url+'/status',timeout=1) as response:state=json.load(response)
                if state.get('version')=='0.4.0':webbrowser.open(url);return
            except Exception:pass
            time.sleep(.25)
    threading.Thread(target=open_when_ready,daemon=True).start()
    return subprocess.call([str(interpreter),'-B',str(ROOT/'app.py')],cwd=ROOT)

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:
        print('启动失败：'+str(error),file=sys.stderr);sys.exit(1)

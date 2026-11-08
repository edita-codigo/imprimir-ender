"""Pecas por texto com a Zoo (zoo.dev, "Zookeeper"): voce descreve a peca, a Zoo desenha (KCL) e o programa vira STL e poe na Mesa 3D.

Como funciona (o REST antigo "text-to-cad" saiu do ar; hoje e por WebSocket):
  1. WebSocket  wss://api.zoo.dev/ws/ml/copilot  com  Authorization: Bearer <chave>
     manda {"type":"user","content":"<descricao>","current_files":{},"forced_tools":["text_to_cad"]}
     recebe {"tool_output":{"result":{"type":"text_to_cad","outputs":{"main.kcl":"<codigo>"}}}} ... {"end_of_stream":{}}
  2. CLI oficial da Zoo (zoo.exe):  zoo kcl export --output-format stl main.kcl <pasta>   (token em ZOO_API_TOKEN)
     transforma o KCL em STL. O programa baixa o zoo.exe do GitHub oficial (KittyCAD/cli) conferindo o SHA-256, se voce mandar.
Chaves: SEM limite, uma por linha, ficam so em _PRIVADO_zoo.json (nunca no log). Se uma esgota o credito ou e recusada, usa a proxima.
Custo: pelo tempo de uso da Zoo (40 min gratis por mes e depois US$0,50/min, segundo a doc oficial; confira na sua conta)."""
import os, re, json, time, hashlib, subprocess, shutil, threading, urllib.request

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_CFG = os.path.join(PASTA, 'zoo.json')
ARQ_CHAVES = os.path.join(PASTA, '_PRIVADO_zoo.json')
PECAS = os.path.join(PASTA, 'pecas_ia')
FERRAMENTAS = os.path.join(PASTA, 'ferramentas', 'zoo')
PADRAO = dict(host='https://api.zoo.dev', cli='', timeout_s=300, permitir_mcp=False, aleatorio=False)
GITHUB = 'https://api.github.com/repos/KittyCAD/cli/releases/latest'
ASSET_WIN = 'zoo-x86_64-pc-windows-gnu'
TEMPO_SEM_CREDITO = 3600
TEMPO_RECUSADA = 12 * 3600
_ruins = {}


class ZooErro(Exception):
    """tipo: 'chave' (recusada ou sem credito: tenta a proxima), 'rede', 'geracao' (a Zoo nao conseguiu desenhar), 'cli' (conversao para STL), 'config'."""
    def __init__(self, msg, tipo='erro'): super().__init__(msg); self.tipo = tipo


# ---------------- configuracao e chaves ----------------
def carregar_cfg():
    c = dict(PADRAO)
    try:
        d = json.load(open(ARQ_CFG, encoding='utf-8'))
        c['host'] = str(d.get('host') or c['host']).rstrip('/'); c['cli'] = str(d.get('cli') or '')
        c['permitir_mcp'] = bool(d.get('permitir_mcp', False)); c['aleatorio'] = bool(d.get('aleatorio', False))
        try: c['timeout_s'] = int(max(30, min(1800, float(d.get('timeout_s', 300)))))
        except (TypeError, ValueError): pass
    except Exception: pass
    return c


def salvar_cfg(c):
    try: json.dump(c, open(ARQ_CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception: pass


def lista_chaves(v):
    """Aceita texto (uma por linha) ou lista. Sem limite de quantidade."""
    if isinstance(v, str): v = re.split(r'[\s,;]+', v)
    out = []
    for k in v or []:
        k = str(k).strip()
        if k and k not in out: out.append(k)
    return out


def carregar_chaves():
    try: return lista_chaves(json.load(open(ARQ_CHAVES, encoding='utf-8')).get('chaves', []))
    except Exception: return []


def salvar_chaves(chaves):
    try: json.dump({'chaves': lista_chaves(chaves)}, open(ARQ_CHAVES, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception: pass


def status_chaves(chaves=None):
    ch = chaves if chaves is not None else carregar_chaves(); agora = time.time()
    return dict(total=len(ch), de_molho=sum(1 for k in ch if _ruins.get(hash(k), 0) > agora))


# ---------------- 1) gerar o KCL ----------------
def gerar_kcl(prompt, token, host, timeout, conectar=None):
    """Pede o desenho a Zoo. Devolve ({arquivo.kcl: codigo}, texto_da_resposta). Levanta ZooErro."""
    from websockets.sync.client import connect
    from websockets.exceptions import InvalidStatus, ConnectionClosed, InvalidHandshake
    conectar = conectar or connect
    url = host.replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/') + '/ws/ml/copilot'
    try:
        ws = conectar(url, additional_headers={'Authorization': 'Bearer ' + token}, open_timeout=30, max_size=64 * 1024 * 1024)
    except InvalidStatus as e:
        code = getattr(getattr(e, 'response', None), 'status_code', 0)
        if code in (401, 403): raise ZooErro('A Zoo recusou a chave (erro %d).' % code, 'chave')
        if code in (402, 429): raise ZooErro('A chave esgotou o credito ou o limite (erro %d).' % code, 'chave')
        raise ZooErro('A Zoo respondeu erro %s ao conectar.' % code, 'rede')
    except (OSError, InvalidHandshake, TimeoutError) as e:
        raise ZooErro('Nao consegui falar com a Zoo: %s' % e, 'rede')
    kcl = {}; texto = []
    with ws:
        ws.send(json.dumps({'type': 'user', 'content': prompt, 'current_files': {}, 'forced_tools': ['text_to_cad']}))
        fim = time.time() + timeout
        while time.time() < fim:
            try: m = ws.recv(timeout=min(60, max(1, fim - time.time())))
            except TimeoutError: continue
            except ConnectionClosed: break
            if isinstance(m, bytes): m = m.decode('utf-8', 'ignore')
            try: msg = json.loads(m)
            except ValueError: continue
            if not isinstance(msg, dict): continue
            if 'access_denied' in msg:
                a = msg['access_denied'] or {}; raise ZooErro('A Zoo negou o acesso (%s): %s' % (a.get('code', '?'), a.get('detail', '')), 'chave')
            if 'error' in msg: raise ZooErro('Erro da Zoo: %s' % (msg['error'] or {}).get('detail', msg['error']), 'geracao')
            if 'delta' in msg: texto.append((msg['delta'] or {}).get('delta', ''))
            if 'tool_output' in msg:
                r = (msg['tool_output'] or {}).get('result') or {}
                if r.get('error'): raise ZooErro('A Zoo nao conseguiu desenhar (%s): %s' % (r.get('status_code', '?'), r['error']), 'geracao')
                for nome, cod in (r.get('outputs') or {}).items(): kcl[str(nome)] = str(cod)
            if 'end_of_stream' in msg: break
    if not kcl: raise ZooErro('A Zoo nao devolveu nenhum desenho. Resposta: %s' % ''.join(texto)[:300], 'geracao')
    return kcl, ''.join(texto)


# ---------------- 2) KCL -> STL ----------------
def achar_cli(cfg=None):
    """Caminho do zoo.exe: o que esta na configuracao, o baixado pelo programa, ou o que estiver no PATH."""
    cfg = cfg or carregar_cfg()
    for c in (cfg.get('cli'), os.path.join(FERRAMENTAS, 'zoo.exe'), shutil.which('zoo') or ''):
        if c and os.path.isfile(c): return c
    return ''


def exportar_stl(kcl, pasta, token, cfg=None, executar=None):
    """Grava o KCL na pasta e roda `zoo kcl export` para gerar o STL. Devolve o caminho do STL."""
    cfg = cfg or carregar_cfg(); cli = achar_cli(cfg)
    if not cli: raise ZooErro('Falta o programa da Zoo (zoo.exe). Na aba "Criar peça" use "Baixar o CLI oficial" ou aponte o caminho.', 'config')
    os.makedirs(pasta, exist_ok=True)
    principal = 'main.kcl' if 'main.kcl' in kcl else sorted(kcl)[0]
    for nome, cod in kcl.items():
        dest = os.path.normpath(os.path.join(pasta, nome))
        if not dest.startswith(os.path.normpath(pasta)): continue         # nunca escreve fora da pasta
        os.makedirs(os.path.dirname(dest), exist_ok=True); open(dest, 'w', encoding='utf-8').write(cod)
    saida = os.path.join(pasta, 'saida'); os.makedirs(saida, exist_ok=True)
    env = dict(os.environ, ZOO_API_TOKEN=token, ZOO_HOST=cfg['host'])
    cmd = [cli, 'kcl', 'export', '--output-format', 'stl', os.path.join(pasta, principal), saida]
    try:
        r = (executar or subprocess.run)(cmd, env=env, capture_output=True, text=True, timeout=cfg['timeout_s'], creationflags=0x08000000)
    except subprocess.TimeoutExpired: raise ZooErro('A conversao para STL demorou demais.', 'cli')
    except OSError as e: raise ZooErro('Nao consegui rodar o zoo.exe: %s' % e, 'cli')
    saida_txt = ((r.stderr or '') + (r.stdout or '')).strip()
    stls = sorted((os.path.join(saida, f) for f in os.listdir(saida) if f.lower().endswith('.stl')), key=os.path.getmtime)
    if r.returncode != 0 or not stls:
        baixo = saida_txt.lower()
        tipo = 'chave' if any(k in baixo for k in ('unauthorized', '401', '403', 'credentials', 'payment', 'credits', '402')) else 'cli'
        raise ZooErro('A conversao para STL falhou: %s' % re.sub(r'\s+', ' ', saida_txt)[-300:], tipo)
    return stls[-1]


# ---------------- tudo junto, com rodizio de chaves ----------------
def texto_para_stl(prompt, chaves=None, cfg=None, aviso=None, gerar=gerar_kcl, exportar=exportar_stl):
    """prompt -> STL (em pecas_ia/). Usa as chaves em sequencia (ou aleatorio), passando para a proxima se uma for recusada/sem credito.
    Devolve dict(stl, pasta, kcl, chave_n, chave_total, texto). `aviso(texto)` recebe o andamento."""
    import random
    cfg = cfg or carregar_cfg(); chaves = lista_chaves(chaves if chaves is not None else carregar_chaves()); aviso = aviso or (lambda t: None)
    prompt = (prompt or '').strip()
    if len(prompt) < 8: raise ZooErro('Descreva a peca com mais detalhe (ex.: "suporte de parede com dois furos de 4 mm, 60 x 20 x 5 mm").', 'config')
    if not chaves: raise ZooErro('Cole pelo menos uma chave da Zoo (aba Criar peça).', 'config')
    agora = time.time(); ordem = list(range(len(chaves)))
    if cfg.get('aleatorio'): random.shuffle(ordem)
    boas = [i for i in ordem if _ruins.get(hash(chaves[i]), 0) <= agora] or [min(ordem, key=lambda j: _ruins.get(hash(chaves[j]), 0))]
    ultimo = None
    for i in boas:
        tk = chaves[i]
        try:
            aviso('Pedindo o desenho a Zoo (chave %d de %d)...' % (i + 1, len(chaves)))
            kcl, texto = gerar(prompt, tk, cfg['host'], cfg['timeout_s'])
            aviso('Desenho pronto. Convertendo para STL...')
            pasta = os.path.join(PECAS, time.strftime('%Y%m%d_%H%M%S_') + (re.sub(r'[^a-z0-9]+', '_', prompt.lower())[:30].strip('_') or 'peca'))
            os.makedirs(pasta, exist_ok=True); open(os.path.join(pasta, 'prompt.txt'), 'w', encoding='utf-8').write(prompt)
            stl = exportar(kcl, pasta, tk, cfg)
            _ruins.pop(hash(tk), None)
            return dict(stl=stl, pasta=pasta, kcl=kcl, texto=texto, chave_n=i + 1, chave_total=len(chaves))
        except ZooErro as e:
            ultimo = e
            if e.tipo == 'chave':
                _ruins[hash(tk)] = agora + (TEMPO_RECUSADA if ('recusou' in str(e) or '401' in str(e) or '403' in str(e)) else TEMPO_SEM_CREDITO)
                aviso('Chave %d: %s Tentando a proxima...' % (i + 1, e)); continue
            raise
    raise ZooErro('Nenhuma das %d chaves funcionou (%s).' % (len(chaves), ultimo), 'chave')


# ---------------- baixar o CLI oficial (com SHA-256) ----------------
def baixar_cli(destino=FERRAMENTAS, url_api=GITHUB, progresso=None, abrir=urllib.request.urlopen):
    """Baixa zoo.exe da release oficial KittyCAD/cli e CONFERE o SHA-256 publicado junto. So guarda se bater."""
    progresso = progresso or (lambda t: None)
    rel = json.loads(abrir(urllib.request.Request(url_api, headers={'User-Agent': 'imprimir-ender'}), timeout=30).read().decode())
    ass = {a['name']: a['browser_download_url'] for a in rel.get('assets', [])}
    if ASSET_WIN not in ass or ASSET_WIN + '.sha256' not in ass: raise ZooErro('A release %s nao tem o arquivo para Windows.' % rel.get('tag_name'), 'config')
    esperado = abrir(urllib.request.Request(ass[ASSET_WIN + '.sha256'], headers={'User-Agent': 'imprimir-ender'}), timeout=30).read().decode().split()[0].strip().lower()
    os.makedirs(destino, exist_ok=True); tmp = os.path.join(destino, 'zoo.exe.baixando'); h = hashlib.sha256(); n = 0
    r = abrir(urllib.request.Request(ass[ASSET_WIN], headers={'User-Agent': 'imprimir-ender'}), timeout=60)
    total = int(r.headers.get('Content-Length') or 0)
    with open(tmp, 'wb') as f:
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b); h.update(b); n += len(b); progresso('Baixando o zoo.exe %d%%' % (100 * n // total) if total else 'Baixando... %d MB' % (n >> 20))
    if h.hexdigest().lower() != esperado:
        os.remove(tmp); raise ZooErro('O arquivo baixado NAO confere com o SHA-256 oficial. Apaguei. Nao use.', 'cli')
    dest = os.path.join(destino, 'zoo.exe')
    if os.path.exists(dest): os.remove(dest)
    os.replace(tmp, dest); return dest, rel.get('tag_name', '')


# ---------------- tarefa em segundo plano (tela e API) ----------------
class Tarefa:
    """Uma geracao por vez, em thread. estado: parado | rodando | pronto | erro."""
    def __init__(self): self.estado = 'parado'; self.msg = ''; self.resultado = None; self.erro = ''; self.prompt = ''; self.inicio = None; self._t = None; self.origem = 'tela'; self.auto_mesa = False

    def iniciar(self, prompt, cfg=None, chaves=None, depois=None):
        if self.estado == 'rodando': return False
        self.estado = 'rodando'; self.msg = 'Comecando...'; self.resultado = None; self.erro = ''; self.prompt = prompt; self.inicio = time.time()
        def run():
            try:
                self.resultado = texto_para_stl(prompt, chaves, cfg, aviso=lambda t: setattr(self, 'msg', t)); self.estado = 'pronto'; self.msg = 'Pronta: %s' % os.path.basename(self.resultado['stl'])
                if depois: depois(self.resultado)
            except ZooErro as e: self.estado = 'erro'; self.erro = str(e); self.msg = str(e)
            except Exception as e: self.estado = 'erro'; self.erro = 'Erro inesperado: %s' % e; self.msg = self.erro
        self._t = threading.Thread(target=run, daemon=True); self._t.start(); return True

    def status(self):
        r = self.resultado
        return dict(estado=self.estado, msg=self.msg, erro=self.erro, prompt=self.prompt, segundos=int(time.time() - self.inicio) if self.inicio and self.estado == 'rodando' else None,
                    stl=r['stl'] if r else None, chave='%s de %s' % (r['chave_n'], r['chave_total']) if r else None)


def listar_pecas():
    """Pecas ja criadas: [{pasta, stl, prompt}] (mais novas primeiro)."""
    out = []
    if os.path.isdir(PECAS):
        for d in sorted(os.listdir(PECAS), reverse=True):
            s = os.path.join(PECAS, d, 'saida')
            if os.path.isdir(s):
                stls = [f for f in os.listdir(s) if f.lower().endswith('.stl')]
                if stls:
                    try: pr = open(os.path.join(PECAS, d, 'prompt.txt'), encoding='utf-8').read()[:200]
                    except Exception: pr = ''
                    out.append(dict(pasta=d, stl=os.path.join(s, stls[0]), prompt=pr))
    return out

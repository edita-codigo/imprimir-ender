"""Vigia por camera: tira uma foto da impressora de tempos em tempos (camera IP), manda para uma IA (JEV/TypeSafe, OpenAI ou Gemini)
e, se achar que a impressao deu errado, avisa o programa (que para a impressora e toca o alarme).
As chaves ficam SO no arquivo _PRIVADO_vigia.json desta pasta (nunca aparecem na tela nem no log)."""
import os, io, json, time, base64, threading, uuid, re
import urllib.request, urllib.error
from PIL import Image

PASTA = os.path.dirname(os.path.abspath(__file__))
CFG_ARQ = os.path.join(PASTA, '_PRIVADO_vigia.json')
FOTOS = os.path.join(PASTA, 'vigia_fotos')
os.makedirs(FOTOS, exist_ok=True)

URLS = {   # enderecos das IAs (os testes trocam por um servidor local de mentira)
    'jev': 'https://api.typesafe.ai/v1/systemone',
    'openai': 'https://api.openai.com/v1/chat/completions',
    'gemini': 'https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent',
}
PROVEDORES = {'jev': 'JEV (TypeSafe)', 'openai': 'OpenAI', 'gemini': 'Gemini'}
MODELOS_PADRAO = {'jev': 'jev-latest', 'openai': 'gpt-4o-mini', 'gemini': 'gemini-2.5-flash'}
MODELOS_SUGERIDOS = {'jev': ['jev-latest'],
                     'openai': ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-4.1', 'gpt-4.1-nano'],
                     'gemini': ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-pro', 'gemini-2.0-flash']}
ACOES = {'esfriar': 'Parar, esfriar e desligar bico e mesa', 'manter': 'Parar e MANTER a temperatura'}

PADRAO = dict(ativo=False, aleatorio=False, camera_url='http://192.168.0.50:8081', flash=True, intervalo_min=5, provedor='jev',
              modelos=dict(MODELOS_PADRAO), chaves={'jev': [], 'openai': [], 'gemini': []},
              limiar=70, confirmar=True, acao='esfriar', desligar_apos_min=30, alarme=True, avisar_falha_ia=True)

TIPOS = {'ok': 'impressão normal', 'espaguete': 'fios soltos e embolados (espaguete)', 'descolou': 'a peça soltou/descolou da mesa',
         'caiu': 'a peça caiu', 'sem_material': 'o bico imprime no ar / sem material', 'camadas_deslocadas': 'camadas deslocadas / peça torta',
         'empenou': 'peça empenada (cantos levantando)', 'outro': 'outro problema', 'nao_avaliavel': 'foto escura ou sem a impressora'}

PROMPT = ('Esta é uma foto de uma impressora 3D (Creality Ender-3 V3 SE, filamento ABS) IMPRIMINDO agora. Procure falhas graves: '
          'fios de filamento soltos e embolados ("espaguete"), peça solta ou descolada da mesa, peça caída, camadas deslocadas ou peça torta, '
          'bico imprimindo no ar sem material saindo, peça empenada com cantos levantando. Se a foto estiver escura, borrada ou sem a impressora, '
          'marque avaliavel=false. Responda SOMENTE um JSON: {"avaliavel": true|false, "probabilidade_falha": numero de 0 a 100, '
          '"tipo": "ok|espaguete|descolou|caiu|sem_material|camadas_deslocadas|empenou|outro|nao_avaliavel", "motivo": "uma frase curta em português"}')


def carregar_cfg():
    cfg = json.loads(json.dumps(PADRAO))
    try:
        d = json.load(open(CFG_ARQ, encoding='utf-8'))
        for k, v in d.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict): cfg[k].update(v)
            else: cfg[k] = v
    except Exception: pass
    return cfg


def salvar_cfg(cfg):
    json.dump(cfg, open(CFG_ARQ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


# ---------------- camera ----------------
def _get(url, timeout=8):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'imprimir-ender-vigia'}), timeout=timeout).read()


def url_foto(base):
    base = (base or '').strip().rstrip('/')
    if not base: raise RuntimeError('Coloque o endereço da câmera (ex.: http://192.168.0.50:8081).')
    if not base.lower().startswith('http'): base = 'http://' + base
    return base if re.search(r'\.(jpe?g|png)(\?.*)?$', base, re.I) or '/shot' in base or 'snapshot' in base.lower() else base + '/shot.jpg'


def capturar(cfg):
    """Tira uma foto (com o flash do celular ligado, se pedido). Devolve bytes da imagem."""
    base = (cfg.get('camera_url') or '').strip().rstrip('/')
    if not base.lower().startswith('http'): base = 'http://' + base
    raiz = re.match(r'(https?://[^/]+)', base).group(1)
    flash = bool(cfg.get('flash'))
    try:
        if flash:
            try: _get(raiz + '/enabletorch', 4); time.sleep(2.0)
            except Exception: flash = False       # camera que nao tem flash: segue sem
        dados = _get(url_foto(cfg.get('camera_url')), 10)
    finally:
        if flash:
            try: _get(raiz + '/disabletorch', 4)
            except Exception: pass
    if len(dados) < 2000: raise RuntimeError('A câmera respondeu, mas não mandou uma foto válida.')
    return dados


def flash(cfg, ligar):
    """Liga/desliga o flash (lanterna) do celular com IP Webcam: /enabletorch e /disabletorch. Devolve texto do resultado."""
    base = (cfg.get('camera_url') or '').strip().rstrip('/')
    if not base: raise RuntimeError('Coloque o endereço da câmera.')
    if not base.lower().startswith('http'): base = 'http://' + base
    raiz = re.match(r'(https?://[^/]+)', base).group(1)
    _get(raiz + ('/enabletorch' if ligar else '/disabletorch'), 5)
    return 'Flash ligado.' if ligar else 'Flash desligado.'


def preparar_imagem(dados, max_lado=1280):
    """JPEG RGB entre 300 e 1280 px (a TypeSafe aceita 280 a 1568 por lado)."""
    im = Image.open(io.BytesIO(dados)).convert('RGB'); w, h = im.size
    esc = min(1.0, max_lado / max(w, h))
    if min(w, h) * esc < 300: esc = 300.0 / min(w, h)
    if abs(esc - 1) > 0.01: im = im.resize((max(280, int(w * esc)), max(280, int(h * esc))), Image.LANCZOS)
    out = io.BytesIO(); im.save(out, 'JPEG', quality=82)
    return out.getvalue()


# ---------------- IAs ----------------
class IAErro(RuntimeError):
    """Erro da IA. codigo = HTTP (429 = cota/limite, 401/403 = chave ruim, 5xx = IA fora); 0 = rede."""
    def __init__(self, msg, codigo=0): super().__init__(msg); self.codigo = codigo


def _post(url, corpo, cabecalhos, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers=dict({'Content-Type': 'application/json'}, **cabecalhos), method='POST')
    try:
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'ignore'))
    except urllib.error.HTTPError as e:      # mostra o motivo sem nunca incluir a chave
        txt = ''
        try: txt = e.read().decode('utf-8', 'ignore')[:200]
        except Exception: pass
        raise IAErro('A IA respondeu erro %s. %s' % (e.code, re.sub(r'\s+', ' ', txt)), e.code)
    except urllib.error.URLError as e:
        raise IAErro('Não consegui falar com a IA: %s' % e.reason, 0)


def _json_do_texto(t):
    t = (t or '').strip()
    t = re.sub(r'^```(?:json)?|```$', '', t, flags=re.M).strip()
    m = re.search(r'\{.*\}', t, re.S)
    return json.loads(m.group(0) if m else t)


def _normalizar(d):
    try: prob = float(d.get('probabilidade_falha', 0))
    except Exception: prob = 0.0
    tipo = str(d.get('tipo', 'outro')).strip().lower()
    aval = d.get('avaliavel', True)
    if isinstance(aval, str): aval = aval.strip().lower() in ('true', 'sim', '1')
    if tipo == 'nao_avaliavel': aval = False
    return dict(ok=bool(aval), prob=max(0.0, min(100.0, prob)), tipo=tipo if tipo in TIPOS else 'outro', motivo=str(d.get('motivo', '')).strip()[:200])


def _jev(jpg, chave, modelo):
    ref = 'foto-' + uuid.uuid4().hex[:8]
    q = {
        'falha': {'type': 'noul', 'instructions': 'Na `foto`, a impressão 3D em andamento tem um problema grave: fios soltos embolados (espaguete), peça solta ou descolada da mesa, peça caída, camadas deslocadas ou peça torta, ou bico imprimindo no ar sem material.'},
        'visivel': {'type': 'noul', 'instructions': 'Na `foto`, a impressora 3D e a peça sendo impressa aparecem com clareza (a foto não está escura nem borrada).'},
        'tipo': {'type': 'choice', 'instructions': 'Qual é o estado da impressão 3D na `foto`', 'criteria': {
            'ok': 'Impressão normal, sem problema', 'espaguete': 'Fios de filamento soltos e embolados (espaguete)', 'descolou': 'A peça soltou ou descolou da mesa',
            'caiu': 'A peça caiu ou foi derrubada', 'sem_material': 'O bico imprime no ar, sem material saindo, ou o filamento acabou',
            'camadas_deslocadas': 'Camadas deslocadas ou peça torta', 'empenou': 'Peça empenada, com os cantos levantando'}}}
    corpo = {'model': modelo or 'jev-latest', 'state': {'foto': ref}, 'assets': {ref: {'type': 'image', 'format': 'jpg', 'data_base64': base64.b64encode(jpg).decode()}}, 'questions': q}
    r = _post(URLS['jev'], corpo, {'Authorization': 'Bearer ' + chave, 'TypeSafe-Danger-Zone-Images': 'true'})
    a = r.get('answers', {})
    falha = float(a.get('falha', {}).get('noul', 0)); vis = float(a.get('visivel', {}).get('noul', 1))
    tp = a.get('tipo', {}); tipo = tp.get('choice', 'ok'); prob = falha * 100
    if tipo != 'ok': prob = max(prob, 100.0 * float(tp.get('probabilities', {}).get(tipo, 0)) * 0.95)
    return dict(ok=vis >= 0.4, prob=prob, tipo=tipo if tipo in TIPOS else 'outro', motivo='JEV: %s (falha %.0f%%, imagem clara %.0f%%)' % (TIPOS.get(tipo, tipo), falha * 100, vis * 100))


def _openai(jpg, chave, modelo):
    corpo = {'model': modelo or 'gpt-4o-mini', 'max_completion_tokens': 300, 'response_format': {'type': 'json_object'},
             'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': PROMPT},
                                                       {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(jpg).decode(), 'detail': 'low'}}]}]}
    r = _post(URLS['openai'], corpo, {'Authorization': 'Bearer ' + chave})
    return _normalizar(_json_do_texto(r['choices'][0]['message']['content']))


def _gemini(jpg, chave, modelo):
    corpo = {'contents': [{'parts': [{'text': PROMPT}, {'inline_data': {'mime_type': 'image/jpeg', 'data': base64.b64encode(jpg).decode()}}]}],
             'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0}}
    r = _post(URLS['gemini'].format(modelo=modelo or 'gemini-2.5-flash'), corpo, {'x-goog-api-key': chave})
    partes = r['candidates'][0]['content']['parts']
    return _normalizar(_json_do_texto(''.join(p.get('text', '') for p in partes)))


def lista_chaves(cfg, prov):
    """Chaves de um provedor, SEM limite de quantidade. Aceita texto (uma por linha/espaco) ou lista (formato antigo = 1 chave)."""
    v = (cfg.get('chaves') or {}).get(prov) or ''
    if isinstance(v, str): v = re.split(r'[\s,;]+', v)
    out = []
    for k in v:
        k = str(k).strip()
        if k and k not in out: out.append(k)
    return out


# chaves que acabaram a cota (429) ou sao ruins (401/403): pulamos por um tempo. So na memoria (nunca grava a chave).
_ruins = {}
_ultimo_uso = {}          # provedor -> indice da ultima chave usada (so para mostrar "chave 2 de 5")
TEMPO_COTA = 3600         # 1 h (a cota por minuto volta logo; a diaria so no dia seguinte, a gente tenta de novo de hora em hora)
TEMPO_RUIM = 12 * 3600


def _id(chave): return hash(chave)


def analisar(cfg, dados):
    """Manda a foto para a IA escolhida. Devolve dict(ok, prob, tipo, motivo, chave_n, chave_total).
    Varias chaves: usa em sequencia (ou aleatoria se cfg['aleatorio']) e passa para a proxima quando uma esgota (429) ou e recusada (401/403)."""
    import random
    prov = cfg.get('provedor', 'jev')
    chaves = lista_chaves(cfg, prov)
    if not chaves: raise RuntimeError('Falta a chave da IA %s (aba Vigia).' % PROVEDORES.get(prov, prov))
    jpg = preparar_imagem(dados)
    modelo = (cfg.get('modelos', {}).get(prov) or MODELOS_PADRAO[prov]).strip()
    fn = {'jev': _jev, 'openai': _openai, 'gemini': _gemini}[prov]
    agora = time.time()
    ordem = list(range(len(chaves)))
    if cfg.get('aleatorio'): random.shuffle(ordem)
    boas = [i for i in ordem if _ruins.get(_id(chaves[i]), 0) <= agora]
    if not boas:                                     # todas de molho: tenta de novo a que volta mais cedo
        i = min(ordem, key=lambda j: _ruins.get(_id(chaves[j]), 0)); boas = [i]
    ultimo_erro = None
    for i in boas:
        try:
            r = fn(jpg, chaves[i], modelo)
        except IAErro as e:
            ultimo_erro = e
            if e.codigo == 429: _ruins[_id(chaves[i])] = agora + TEMPO_COTA
            elif e.codigo in (401, 403): _ruins[_id(chaves[i])] = agora + TEMPO_RUIM
            else: raise                                # IA fora do ar / rede: trocar de chave nao adianta
            continue
        _ruins.pop(_id(chaves[i]), None); _ultimo_uso[prov] = i
        r['jpg'] = jpg; r['provedor'] = prov; r['chave_n'] = i + 1; r['chave_total'] = len(chaves)
        return r
    raise RuntimeError('Todas as %d chaves de %s esgotaram ou foram recusadas (%s). Cole outra chave ou espere a cota voltar.' % (len(chaves), PROVEDORES.get(prov, prov), str(ultimo_erro)[:120]))


def status_chaves(cfg, prov=None):
    """Resumo para a tela (sem mostrar chave): quantas ha, quantas de molho."""
    prov = prov or cfg.get('provedor', 'jev'); ch = lista_chaves(cfg, prov); agora = time.time()
    return dict(total=len(ch), de_molho=sum(1 for k in ch if _ruins.get(_id(k), 0) > agora), ultima=_ultimo_uso.get(prov))


# ---------------- o vigia (fica de olho enquanto imprime) ----------------
class Vigia:
    def __init__(self, app):
        self.app = app; self.cfg = carregar_cfg()
        self.thread = None; self.parar = threading.Event()
        self.ultimo = None; self.historico = []; self.foto_nova = False; self.estado = 'desligado'; self.erros = 0; self.aviso_ia = False
        self.proxima = None

    # --- uma checagem (foto + IA); usado pelo vigia e pelo botao "Testar agora" ---
    def checar(self):
        dados = capturar(self.cfg)
        r = analisar(self.cfg, dados); r['hora'] = time.strftime('%H:%M:%S'); r['original'] = dados
        self._guardar(r); return r

    def _guardar(self, r):
        self.ultimo = r; self.foto_nova = True
        self.historico.append(dict(hora=r['hora'], prob=r['prob'], tipo=r['tipo'], motivo=r['motivo'], ok=r['ok'])); self.historico = self.historico[-60:]
        try:
            nome = os.path.join(FOTOS, time.strftime('%Y%m%d_%H%M%S_') + '%d.jpg' % int(r['prob']))
            open(nome, 'wb').write(r['jpg'])
            fs = sorted(os.listdir(FOTOS))
            for f in fs[:-40]: os.remove(os.path.join(FOTOS, f))     # guarda so as ultimas 40
        except Exception: pass

    def iniciar(self):
        self.cfg = carregar_cfg()
        if not self.cfg.get('ativo') or (self.thread and self.thread.is_alive()): return False
        self.parar.clear(); self.erros = 0; self.aviso_ia = False; self.estado = 'ligado'
        self.thread = threading.Thread(target=self._rodar, daemon=True); self.thread.start(); return True

    def encerrar(self):
        self.parar.set(); self.estado = 'desligado'; self.proxima = None

    def _esperar(self, seg):
        fim = time.time() + seg; self.proxima = fim
        while time.time() < fim:
            if self.parar.is_set() or not self.app.imprimindo: return False
            time.sleep(0.5)
        return True

    def _rodar(self):
        try:
            # 1a checagem 3 min depois de comecar a peca (pega peca que nao grudou); depois a cada 'intervalo_min'
            while not self.parar.is_set() and self.app.imprimindo and self.app.st.get('etapa', 0) < 5: time.sleep(1)
            if not self._esperar(180): return
            while not self.parar.is_set() and self.app.imprimindo:
                self._ciclo()
                if not self._esperar(max(1, float(self.cfg.get('intervalo_min', 5))) * 60): break
        finally:
            self.estado = 'desligado'; self.proxima = None

    def _ciclo(self):
        c = self.cfg; self.estado = 'olhando'
        try:
            r = self.checar(); self.erros = 0
        except Exception as e:
            self.erros += 1; self.estado = 'ligado'; self.app.say('Vigia: erro (%s) [%d]' % (str(e)[:150], self.erros))
            if self.erros >= 3 and not self.aviso_ia and c.get('avisar_falha_ia', True):
                self.aviso_ia = True; self.app.vigia_aviso('O vigia não está conseguindo olhar a impressora (%s). A impressão continua, SEM vigilância.' % str(e)[:150])
            return
        self.app.say('Vigia: %s, falha %.0f%% (%s)' % ('ok' if r['prob'] < c.get('limiar', 70) else 'SUSPEITO', r['prob'], r['tipo']))
        if r['ok'] and r['prob'] >= float(c.get('limiar', 70)):
            if c.get('confirmar', True):       # evita alarme falso: tira outra foto 30 s depois
                self.estado = 'confirmando'
                if not self._esperar(30): return
                try: r2 = self.checar()
                except Exception: r2 = r
                self.app.say('Vigia (confirmação): falha %.0f%% (%s)' % (r2['prob'], r2['tipo']))
                if not (r2['ok'] and r2['prob'] >= float(c.get('limiar', 70))): self.estado = 'ligado'; return
                r = r2
            self.estado = 'ALERTA'
            self.app.vigia_falha(r)
            self.parar.set()


def listar_modelos(cfg, prov):
    """Pergunta ao provedor quais modelos a chave 1 enxerga (so os que olham imagem/texto). Sugeridos + os da conta. Nunca devolve a chave."""
    sug = list(MODELOS_SUGERIDOS.get(prov, []))
    chaves = lista_chaves(cfg, prov)
    if prov == 'jev' or not chaves: return sug, 'Mostrando só os sugeridos' + ('' if chaves else ' (sem chave cadastrada para buscar)') + '.'
    try:
        if prov == 'openai':
            req = urllib.request.Request('https://api.openai.com/v1/models', headers={'Authorization': 'Bearer ' + chaves[0]})
            ids = [m['id'] for m in json.loads(urllib.request.urlopen(req, timeout=20).read().decode())['data']]
            ids = [i for i in ids if i.startswith(('gpt-4', 'gpt-5', 'o3', 'o4', 'chatgpt')) and not any(x in i for x in ('audio', 'realtime', 'tts', 'transcribe', 'search', 'image', 'embedding', 'moderation', 'instruct'))]
        else:
            req = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models?pageSize=200', headers={'x-goog-api-key': chaves[0]})
            ms = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())['models']
            ids = [m['name'].split('/')[-1] for m in ms if 'generateContent' in m.get('supportedGenerationMethods', []) and m['name'].split('/')[-1].startswith('gemini') and not any(x in m['name'] for x in ('embedding', 'tts', 'image', 'live', 'audio'))]
        out = sug + sorted(i for i in set(ids) if i not in sug)
        return out, '%d modelos encontrados na sua chave.' % len(set(ids))
    except urllib.error.HTTPError as e: return sug, 'A chave foi recusada (erro %s). Mostrando só os sugeridos.' % e.code
    except Exception as e: return sug, 'Não consegui buscar (%s). Mostrando só os sugeridos.' % type(e).__name__

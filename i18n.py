"""Idiomas do programa: pt (original), en, es, ru.
Como funciona: o programa foi escrito em portugues; os textos que vao para a tela (botoes, rotulos, mensagens, avisos) passam por tr(), que procura a traducao em
idiomas/<codigo>.json  ({"texto em portugues": "traducao"}). Textos com valores (ex.: 'Pausa: %s') tambem sao traduzidos: a chave e o formato original.
Se nao ha traducao, aparece o texto original em portugues (nunca fica em branco). Para acrescentar um idioma: crie idiomas/<codigo>.json e ponha o codigo em IDIOMAS.
"""
import os, re, json, sys
import tkinter as tk
from tkinter import messagebox

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'idiomas')
ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'idioma.json')
IDIOMAS = {'pt': 'Português', 'en': 'English', 'es': 'Español', 'ru': 'Русский'}
_estado = {'cod': 'pt', 'dic': {}, 'pad': []}
_FMT = re.compile(r'%[-+ 0#]*\d*(?:\.\d+)?[sdifxXeEgG]')


def detectar_do_sistema():
    try:
        import ctypes
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x16: 'pt', 0x0A: 'es', 0x19: 'ru'}.get(lid, 'en')
    except Exception:
        return 'en'


def salvo():
    try:
        c = json.load(open(ARQ, encoding='utf-8')).get('idioma')
        if c in IDIOMAS: return c
    except Exception: pass
    return None


def atual(): return _estado['cod']


def _compilar(dic):
    """Chaves com %s/%d... viram padroes: 'Pausa: %s' casa 'Pausa: motivo X'."""
    pad = []
    for k, v in dic.items():
        if not _FMT.search(k): continue
        partes = _FMT.split(k); rx = '(?s)^' + '(.+?)'.join(re.escape(p) for p in partes) + '$'
        try: pad.append((re.compile(rx), v, sum(len(p) for p in partes)))
        except re.error: continue
    pad.sort(key=lambda x: -x[2])
    return pad


def carregar(cod):
    _estado['cod'] = cod if cod in IDIOMAS else 'pt'; _estado['dic'] = {}; _estado['pad'] = []
    if _estado['cod'] == 'pt': return
    dic = {}
    for nome in sorted(os.listdir(PASTA)) if os.path.isdir(PASTA) else []:       # en.json, en_2.json, en_extra.json... (todos somam; web_*.json e _*.json ficam de fora)
        if nome.startswith(_estado['cod'] + '.') or nome.startswith(_estado['cod'] + '_'):
            try:
                d = json.load(open(os.path.join(PASTA, nome), encoding='utf-8'))
                dic.update({k: v for k, v in d.items() if isinstance(v, str) and v})
            except Exception: pass
    _estado['dic'] = dic; _estado['pad'] = _compilar(dic)


def definir(cod, gravar=True):
    carregar(cod)
    if gravar:
        try: json.dump({'idioma': _estado['cod']}, open(ARQ, 'w', encoding='utf-8'))
        except Exception: pass


def _um(s):
    d = _estado['dic']
    if s in d: return d[s]
    for rx, fmt, _n in _estado['pad']:
        m = rx.match(s)
        if m:
            partes = _FMT.split(fmt); valores = list(m.groups()); out = partes[0]
            if len(partes) - 1 != len(valores): continue
            for i, v in enumerate(valores): out += tr(v) + partes[i + 1]
            return out
    return None


def tr(s):
    """Traduz um texto da interface. Sem traducao: devolve o original."""
    if _estado['cod'] == 'pt' or not isinstance(s, str) or not s.strip(): return s
    base = s.strip()
    ini, fim = s[:len(s) - len(s.lstrip())], s[len(s.rstrip()):]
    r = _um(base)
    if r is not None: return ini + r + fim
    for sep in ('\n', ' · ', ' | '):                      # mensagens montadas por partes
        if sep in base:
            return ini + sep.join(tr(p) if p.strip() else p for p in base.split(sep)) + fim
    return s


_instalado = [False]


def instalar():
    """Liga a traducao automatica nos pontos por onde o texto chega a tela (widgets, menus, titulos e caixas de mensagem)."""
    if _instalado[0]: return
    _instalado[0] = True
    orig = tk.Misc._options

    def _options(self, cnf, kw=None):
        if _estado['cod'] != 'pt':
            if kw and ('text' in kw or 'label' in kw):
                kw = dict(kw)
                for k in ('text', 'label'):
                    if isinstance(kw.get(k), str): kw[k] = tr(kw[k])
            if isinstance(cnf, dict) and ('text' in cnf or 'label' in cnf):
                cnf = dict(cnf)
                for k in ('text', 'label'):
                    if isinstance(cnf.get(k), str): cnf[k] = tr(cnf[k])
        return orig(self, cnf, kw)
    tk.Misc._options = _options
    o_title = tk.Wm.wm_title

    def wm_title(self, string=None):
        return o_title(self, tr(string) if isinstance(string, str) else string)
    tk.Wm.wm_title = wm_title; tk.Wm.title = wm_title
    for nome in ('showinfo', 'showwarning', 'showerror', 'askyesno', 'askokcancel', 'askquestion', 'askretrycancel', 'askyesnocancel'):
        f = getattr(messagebox, nome, None)
        if f is None: continue

        def envolver(f):
            def g(title=None, message=None, **kw):
                return f(tr(title) if isinstance(title, str) else title, tr(message) if isinstance(message, str) else message, **kw)
            return g
        setattr(messagebox, nome, envolver(f))


def instalar_no_app(App):
    """say() (linha de status/registro) e avisar() (celular) tambem traduzem."""
    for nome in ('say',):
        f = getattr(App, nome, None)
        if f:
            def envolver(f):
                def g(self, t, *a, **k): return f(self, tr(t), *a, **k)
                return g
            setattr(App, nome, envolver(f))


# idioma inicial: o que o usuario escolheu; senao o do Windows
carregar(salvo() or detectar_do_sistema())

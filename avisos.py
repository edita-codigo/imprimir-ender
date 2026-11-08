"""Avisos no celular (Pushover) do programa Imprimir Ender.
Usa o script que ja existe no PC (notificar_pushover.py, com as credenciais la dentro): nada de chave aqui.
Tudo em thread e sem derrubar o programa se falhar."""
import os, json, threading, importlib.util, time

PASTA = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get('ENDER_PUSHOVER_SCRIPT', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notificar_pushover.py'))   # opcional: seu script com notificar(titulo, texto)
CFG = os.path.join(PASTA, 'avisos.json')
PADRAO = dict(pushover=True, terminou=True, erro=True, vigia=True, tirar_peca=True, filamento=True, pausa=True)
TITULO = 'Imprimir Ender'
_mod = None
ultimo = dict(hora='', texto='', ok=None, erro='')     # o que foi enviado por ultimo (aparece na tela)


def carregar():
    c = dict(PADRAO)
    try: c.update(json.load(open(CFG, encoding='utf-8')))
    except Exception: pass
    return c


def salvar(c):
    try: json.dump(c, open(CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception: pass


def _notificar():
    """Carrega a funcao notificar() do script do Pushover (uma vez)."""
    global _mod
    if _mod is None:
        if not os.path.isfile(SCRIPT): raise RuntimeError('script do Pushover nao encontrado')
        spec = importlib.util.spec_from_file_location('notificar_pushover_ender', SCRIPT)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); _mod = m
    return _mod.notificar


def enviar(texto, titulo=TITULO, prioridade=0, tipo=None, cfg=None, log=None):
    """Manda o aviso em segundo plano. 'tipo' = qual chave de avisos.json controla (terminou, erro, vigia, tirar_peca, filamento, pausa).
    Devolve False se o aviso esta desligado."""
    c = cfg or carregar()
    if not c.get('pushover', True): return False
    if tipo and not c.get(tipo, True): return False
    def run():
        try:
            _notificar()(texto[:1000], titulo[:100], prioridade)
            ultimo.update(hora=time.strftime('%H:%M:%S'), texto=texto[:120], ok=True, erro='')
            if log: log('Aviso enviado ao celular: ' + texto[:60])
        except Exception as e:
            ultimo.update(hora=time.strftime('%H:%M:%S'), texto=texto[:120], ok=False, erro=str(e)[:120])
            if log: log('Aviso ao celular FALHOU: %s' % str(e)[:100])
    threading.Thread(target=run, daemon=True).start()
    return True

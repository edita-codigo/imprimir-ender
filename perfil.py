"""Perfil da impressora (tudo que muda de uma impressora para outra fica AQUI, nao no codigo).

Arquivo: perfil_impressora.json (na pasta do programa). O padrao e a Creality Ender-3 V3 SE.
Para outra impressora: copie o arquivo, ajuste os valores (tamanho da mesa, onde cuspir o filamento, etc.) e pronto.
Se uma chave faltar no arquivo, vale o padrao abaixo."""
import os, json, copy

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(PASTA, 'perfil_impressora.json')

PADRAO = {
    'nome': 'Creality Ender-3 V3 SE',
    'mesa': {'x': 220, 'y': 220, 'z': 245},       # area util (mm)
    # onde o bico CUSPE o filamento na troca de cor (canto da frente, a esquerda; a tela fica na frente, a direita).
    # Coloque uma lixeirinha embaixo. Use o botao "Testar posicao" da aba Cores para conferir antes.
    'cuspir': {
        'x': 5.0, 'y': 5.0, 'z': 30.0,       # posicao do bico (mm) e altura de seguranca
        'purga_mm': 40,                      # filamento empurrado depois de carregar o novo (tira a cor antiga do bico)
        'purga_extra_mm': 10,                # cada toque em "purgar mais"
        'descarregar_mm': 80,                # quanto puxa para soltar o filamento velho
        'carregar_mm': 60,                   # quanto empurra para o filamento novo chegar no bico
        'espera_max_min': 15,                # se demorar mais que isso para trocar, o bico esfria um pouco (nao queimar o ABS parado)
        'temp_espera': 170,                  # temperatura de espera
    },
}


def _mesclar(base, novo):
    for k, v in (novo or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict): _mesclar(base[k], v)
        else: base[k] = v
    return base


def carregar():
    p = copy.deepcopy(PADRAO)
    try: _mesclar(p, json.load(open(ARQ, encoding='utf-8')))
    except Exception: pass
    return p


def salvar(p):
    json.dump(p, open(ARQ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def cuspir():
    """Configuracao de cuspir/trocar filamento (com numeros ja convertidos)."""
    c = carregar()['cuspir']
    return {k: float(v) for k, v in c.items()}

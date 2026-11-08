"""Ferramenta para ACRESCENTAR um idioma ao programa (ou completar textos novos) usando a API do Claude (modelo barato, em lotes).
Nao faz parte do programa de impressao: so quem traduz precisa dela. Uso:

    set ANTHROPIC_API_KEY=sua_chave          (ou grave a chave em _PRIVADO_traducao.json: {"chave": "..."} - NUNCA publique esse arquivo)
    python traduzir_idiomas.py --codigo fr --nome "Français"            # cria idiomas/fr.json com tudo que o programa mostra
    python traduzir_idiomas.py --codigo en --so-faltando                 # traduz so os textos novos que ainda nao estao em idiomas/en*.json
    python traduzir_idiomas.py --codigo fr --nome "Français" --simular   # mostra quantos textos e o custo aproximado, sem chamar a API

Depois acrescente o idioma em i18n.IDIOMAS (codigo e nome) e reinicie o programa. Regras que a ferramenta confere em cada traducao: mesmos marcadores %s/%d/%.1f e mesmas quebras de linha.
"""
import ast, os, re, sys, json, time, argparse
import urllib.request, urllib.error

PASTA = os.path.dirname(os.path.abspath(__file__))
IDI = os.path.join(PASTA, 'idiomas')
ARQUIVOS = ['imprimir_ender.py', 'mesa3d.py', 'cores.py', 'suporte.py', 'avancado_ui.py', 'zoo_ui.py', 'mcp_ui.py', 'editar_ui.py', 'testes_ui.py', 'testes_hw.py', 'manual.py', 'fila.py', 'vista3d.py',
            'nivelar.py', 'calibracao.py', 'custo.py', 'timelapse.py', 'vigia.py', 'avisos.py', 'perfil.py', 'editar_peca.py', 'zoo_cad.py', 'avancado.py', 'base_ender.py']
MODELO = 'claude-haiku-5-5'
FMT = re.compile(r'%[-+ 0#]*\d*(?:\.\d+)?[sdifgxXeE%]')
BARRA = chr(92)


def extrair():
    """Todos os textos em portugues que o programa pode mostrar (constantes de texto dos modulos, menos docstrings, codigo, caminhos e G-code)."""
    achados = {}; doc = set()
    for f in ARQUIVOS:
        try: t = ast.parse(open(os.path.join(PASTA, f), encoding='utf-8').read())
        except Exception: continue
        for n in ast.walk(t):
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str): doc.add(n.value.value)
        for n in ast.walk(t):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                v = n.value; s = v.strip()
                if v in doc or len(v) < 3 or len(v) > 500 or not re.search(r'[A-Za-zÀ-ÿ]{2}', v): continue
                if BARRA in v or s.startswith((';', '*.', '(', '=', '$', '^', '#', '<', '{', '[', 'http', 'import', 'def ')): continue
                if re.fullmatch(r'[a-z_0-9./:\-]+', v) or re.fullmatch(r'[%\w.\-]*\.(jpg|stl|gcode|txt|json|png|exe)', s): continue
                if re.search(r'\b(G[0-9]{1,2}|M[0-9]{2,3})\b.*\b[XYZEFSPT]-?\d', s): continue
                if ' ' not in s and not re.search(r'[À-ÿ]', s) and s.lower() == s: continue
                achados[v] = f
    return sorted(achados)


def carregar_chave():
    k = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if k: return k
    try: return json.load(open(os.path.join(PASTA, '_PRIVADO_traducao.json'), encoding='utf-8')).get('chave', '').strip()
    except Exception: return ''


def ja_traduzidos(cod):
    d = {}
    if os.path.isdir(IDI):
        for n in os.listdir(IDI):
            if n.startswith(cod + '.') or n.startswith(cod + '_'):
                try: d.update(json.load(open(os.path.join(IDI, n), encoding='utf-8')))
                except Exception: pass
    return d


def chamar(chave, nome, textos):
    sistema = ('Voce traduz a interface de um programa de impressora 3D (Creality Ender-3 V3 SE) do portugues do Brasil para %s. Responda SOMENTE um array JSON de strings, na MESMA ordem e quantidade da entrada. '
               'Regras: preserve exatamente os marcadores de formatacao (%%s %%d %%.1f %%g %%%% ...) na mesma ordem, as quebras de linha (\\n) e espacos nas pontas; nao traduza siglas e nomes tecnicos (STL, 3MF, G-code, ABS, PLA, MCP, API, CuraEngine, Marlin, CR Touch, Zoo, X/Y/Z), '
               'nomes de arquivo, numeros e unidades; botoes e rotulos curtos e naturais (MAIUSCULAS se o original estiver); se o texto nao for portugues traduzivel, copie igual.') % nome
    corpo = {'model': MODELO, 'max_tokens': 8000, 'system': sistema, 'messages': [{'role': 'user', 'content': json.dumps(textos, ensure_ascii=False)}]}
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=json.dumps(corpo).encode(), headers={'x-api-key': chave, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    r = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
    txt = ''.join(b.get('text', '') for b in r.get('content', []))
    m = re.search(r'\[.*\]', txt, re.S)
    return json.loads(m.group(0) if m else txt)


def confere(orig, trad):
    return isinstance(trad, str) and FMT.findall(orig) == FMT.findall(trad) and orig.count('\n') == trad.count('\n')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--codigo', required=True); ap.add_argument('--nome', default=''); ap.add_argument('--so-faltando', action='store_true'); ap.add_argument('--simular', action='store_true'); ap.add_argument('--lote', type=int, default=40)
    a = ap.parse_args(); cod = a.codigo.lower()
    textos = extrair(); feitos = ja_traduzidos(cod) if a.so_faltando else {}
    pend = [t for t in textos if t not in feitos]
    print('%d textos no programa, %d a traduzir.' % (len(textos), len(pend)))
    if a.simular or not pend:
        print('Custo aproximado: ~%d mil caracteres de entrada (centavos de dolar com o modelo %s).' % (sum(len(t) for t in pend) // 1000 + 1, MODELO)); return
    chave = carregar_chave()
    if not chave: print('Sem chave: defina ANTHROPIC_API_KEY ou crie _PRIVADO_traducao.json com {"chave": "..."}'); sys.exit(1)
    nome = a.nome or cod; saida = {}; falhas = []
    for i in range(0, len(pend), a.lote):
        lote = pend[i:i + a.lote]
        for tentativa in (1, 2, 3):
            try:
                tr = chamar(chave, nome, lote)
                if len(tr) != len(lote): raise ValueError('quantidade diferente')
                for o, t in zip(lote, tr):
                    if confere(o, t): saida[o] = t
                    else: falhas.append(o)
                break
            except (urllib.error.URLError, ValueError, json.JSONDecodeError) as e:
                print('  lote %d tentativa %d falhou: %s' % (i // a.lote + 1, tentativa, e)); time.sleep(3)
        else: falhas += lote
        print('  %d/%d' % (min(i + a.lote, len(pend)), len(pend)), flush=True)
    os.makedirs(IDI, exist_ok=True)
    arq = os.path.join(IDI, cod + ('_novos.json' if a.so_faltando else '.json'))
    json.dump(saida, open(arq, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('Gravado %s (%d textos). %d ficaram sem traducao confiavel (marcadores/quebras nao bateram): vao aparecer em portugues.' % (arq, len(saida), len(set(falhas) - set(saida))))
    print('Falta so acrescentar "%s": "%s" em i18n.IDIOMAS (se for um idioma novo).' % (cod, nome))


if __name__ == '__main__':
    main()

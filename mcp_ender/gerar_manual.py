"""Gera MANUAL_MCP.md a partir das ferramentas REAIS de server.py (nome, parametros e descricao). Rode: python gerar_manual.py
Assim o manual nunca fica desatualizado: ao criar uma ferramenta nova no server.py, rode de novo."""
import ast, os, re

PASTA = os.path.dirname(os.path.abspath(__file__))
GRUPOS = [
    ('Estado e controle da impressora', ('ender_status', 'ender_log', 'ender_enviar_arquivo', 'ender_imprimir', 'ender_parar', 'ender_pausar', 'ender_continuar', 'ender_purgar', 'ender_testar_sensor', 'ender_fila', 'ender_gcode')),
    ('Diagnóstico das peças da impressora', ('ender_diagnostico_lista', 'ender_diagnostico')),
    ('Câmera e vigia', ('ender_flash', 'ender_foto', 'ender_vigia_testar', 'ender_vigia_ativar')),
    ('Mesa 3D (peças, cores, suporte)', ('ender_mesa_', 'ender_suporte_')),
    ('Impressão colorida', ('ender_cores_',)),
    ('Modelar: criar e editar peças por passos (CAD)', ('ender_modelar_',)),
    ('Editar peça (antigo; prefira Modelar)', ('ender_editar_',)),
    ('Criar peça por texto (Zoo)', ('ender_peca_',)),
    ('Modo avançado (início/fim, ventoinha, G-code extra)', ('ender_avancado_',)),
]


def ferramentas():
    arv = ast.parse(open(os.path.join(PASTA, 'server.py'), encoding='utf-8').read()); out = []
    for n in arv.body:
        if isinstance(n, ast.FunctionDef) and any((isinstance(d, ast.Call) and getattr(d.func, 'attr', '') == 'tool') or (isinstance(d, ast.Attribute) and d.attr == 'tool') or 'tool' in ast.dump(d) for d in n.decorator_list) and n.name.startswith('ender_'):
            args = []
            for i, a in enumerate(n.args.args):
                padrao = n.args.defaults[i - (len(n.args.args) - len(n.args.defaults))] if i >= len(n.args.args) - len(n.args.defaults) else None
                t = ast.unparse(a.annotation) if a.annotation else ''
                args.append(a.arg + (': ' + t if t else '') + (' = ' + ast.unparse(padrao) if padrao is not None else ''))
            out.append((n.name, args, (ast.get_docstring(n) or '').strip()))
    return out


def main():
    fs = ferramentas(); usados = set(); linhas = []
    linhas.append('# Manual do MCP "ender-impressora"\n')
    linhas.append('Este MCP deixa uma IA (Claude Code, Claude Desktop, Cursor, qualquer cliente MCP) **controlar o programa Imprimir Ender**: olhar a impressora, mexer na Mesa 3D, trocar cores, editar peças, criar peças por texto e rodar diagnóstico. '
                  'Ele NÃO fala com a impressora direto: chama a API do programa (`servidor_rede.py`, portas 8101 a 8110), então todas as travas de segurança do programa continuam valendo. **O programa precisa estar aberto.**\n')
    linhas.append('## Como ligar\n1. No programa, aba **IA / MCP**: copie o comando do Claude Code (ou o JSON para outros clientes), ou clique em "Registrar no Claude Code agora".\n'
                  '2. O MCP lê o token de `_PRIVADO_token_rede.txt` (pasta do programa) ou da variável `ENDER_TOKEN`. Ao "Gerar novo token" na aba, o MCP deste PC continua funcionando sozinho. **Nunca publique esse arquivo.**\n'
                  '3. A aba tem também **SOMENTE LEITURA** (a IA só olha; o PARAR continua valendo).\n'
                  '4. Para outra IA fora do MCP, a aba mostra um texto pronto (endereço + token) para colar.\n')
    linhas.append('## Regras de segurança (valem para a IA)\n- Nunca iniciar impressão sem o usuário pedir. `ender_imprimir` exige `confirmo=true`.\n- Testes que aquecem/mexem a impressora e criação de peça pela Zoo exigem `confirmo=true` (e, na Zoo, a permissão marcada na aba Criar peça).\n'
                  '- G-code livre só com a impressora parada e só comandos da lista segura (bloqueia M112, M500, M502, M92 etc.; bico ≤ 275 °C, mesa ≤ 110 °C).\n- A edição de peça nunca altera o arquivo original: salva uma cópia em `pecas_editadas`.\n- Erro do programa volta como `{"ok": false, "erro": ...}`.\n')
    linhas.append('## Ferramentas\n')
    for titulo, prefixos in GRUPOS:
        grupo = [f for f in fs if f[0] in prefixos or any(f[0].startswith(p) for p in prefixos if p.endswith('_'))]
        grupo = [f for f in grupo if f[0] not in usados]
        if not grupo: continue
        linhas.append('### %s\n' % titulo)
        for nome, args, doc in grupo:
            usados.add(nome)
            linhas.append('**`%s(%s)`**  \n%s\n' % (nome, ', '.join(args), re.sub(r'\s*\n\s*', ' ', doc)))
    resto = [f for f in fs if f[0] not in usados]
    if resto:
        linhas.append('### Outras\n')
        for nome, args, doc in resto: linhas.append('**`%s(%s)`**  \n%s\n' % (nome, ', '.join(args), re.sub(r'\s*\n\s*', ' ', doc)))
    linhas.append('## Receitas\n')
    linhas.append('**Editar uma peça que está na mesa**\n1. `ender_mesa_ver` → veja os ids. 2. `ender_editar_abrir(id_peca=1)` → tamanho e coordenadas. 3. `ender_editar_ver` → olhe a peça. '
                  '4. Faça os passos (`ender_editar_furo`, `ender_editar_texto`, `ender_editar_forma`, `ender_editar_desenhar`...) e confira com `ender_editar_ver` depois de cada um. 5. `ender_editar_desfazer` se errar. 6. `ender_editar_salvar` (copia para a mesa).\n')
    linhas.append('**Desenhar à mão** (ex.: pino, suporte, gancho): `ender_editar_desenhar` recebe um polígono (lista de pontos em mm) e a espessura. Use as mesmas coordenadas de `min`/`max` de `ender_editar_estado`. Para curvas, use muitos pontos. '
                  'Para um furo redondo use `ender_editar_furo`; para um recorte qualquer use `ender_editar_desenhar` com `modo="subtrair"`.\n')
    linhas.append('**Peça colorida (3MF)**: `ender_mesa_importar_3mf` → cada parte vira uma peça com a cor lida do arquivo (nome da parte, extrusor ou material). '
                  '`ender_mesa_so_cor("Vermelho")` deixa só uma cor na mesa; imprima, troque o filamento, e repita com a próxima cor; `ender_mesa_so_cor("todas")` traz tudo de volta. Se uma peça não couber na mesa, use `ender_mesa_editar(id, escala=...)`.\n')
    linhas.append('**Diagnóstico**: `ender_diagnostico()` (só leitura) → firmware, termistores, fins de curso, sensor de filamento, SD, tela e ventoinha. '
                  'Com `permitir_aquecer`/`permitir_mover`/`permitir_extrusor` + `confirmo=true` ele testa também o aquecimento, os motores e o extrusor. Resultados `observar` pedem confirmação humana (pergunte ao usuário se viu/ouviu).\n')
    linhas.append('**Imprimir**: `ender_status` (livre?) → `ender_enviar_arquivo` ou monte a mesa e `ender_mesa_fatiar` → confira tempo e custo → o usuário autoriza → `ender_imprimir(confirmo=true)` → `ender_status` de tempos em tempos, `ender_foto` para olhar.\n')
    open(os.path.join(PASTA, 'MANUAL_MCP.md'), 'w', encoding='utf-8').write('\n'.join(linhas))
    print('manual gerado com %d ferramentas' % len(fs))


if __name__ == '__main__':
    main()

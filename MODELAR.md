# Aba Modelar (criar e editar peças em 3D)

Modelagem de verdade (CAD) dentro do programa: cria peça do zero, edita peça pronta (STL/STEP), várias peças abertas ao mesmo tempo, e tudo o que a tela faz a IA também faz pelo MCP.

## Como funciona
- A peça é uma **receita de passos** (como a linha do tempo do Fusion). Cada passo é uma ferramenta com medidas. Mudou uma medida de um passo antigo, a peça inteira é refeita.
- Motor: **build123d / OpenCascade** (`pip install build123d`). Sólidos exatos: arredondar, chanfrar, casca, STEP.
- Peça vinda de **STL** vira malha: dá para somar formas, furar, cortar, escrever, mover e espelhar (via manifold3d). Arredondar, chanfrar e casca só em peça criada aqui ou vinda de STEP.
- Medidas em mm. X = direita, Y = fundo, Z = cima; a mesa é Z = 0. Nas formas, (x, y) é o centro e z é a base.
- Toda medida aceita conta e variável: `40/2`, `largura - 2*folga`.

## Ferramentas (25)
| Grupo | Ferramentas |
|---|---|
| Criar | caixa, cilindro, tubo, esfera, cone, toro (rosquinha), prisma, cunha (rampa), texto (relevo/gravado nas 6 faces) |
| Desenho | extrudar, revolução, loft (transição), varrer: usam o desenho 2D feito com o mouse (retângulo, círculo, elipse, polígono regular, rasgo, polígono livre, texto; a IA também usa linhas e arcos) |
| Modificar | arredondar, chanfrar, casca, furo (simples, rebaixado, escareado), cortar |
| Mover | mover, girar, escalar, espelhar, assentar |
| Avançado | importar (STL/3MF/OBJ/STEP), código (build123d livre; desligado por padrão, liga em "Usar IA") |

Extras: **repetir** (fila, grade ou círculo) em qualquer forma ou furo; modo **somar / tirar / só onde cruza / novo**; **variáveis** do projeto.

## Na tela
- Faixa de ferramentas em cima; passos à esquerda (clique para mudar medidas, olho desliga, lixeira apaga); medidas da ferramenta à direita.
- Antes de aplicar, a ferramenta aparece em **vermelho transparente** na peça.
- **Clicar na peça**: aresta (para arredondar/chanfrar) ou face (para furo/casca); Shift = várias. Com o Furo aberto, o clique marca posição e direção.
- Mouse na vista: arrastar = girar, botão direito = deslocar, roda = zoom, duplo clique = enquadrar.
- Projetos salvos sozinhos em `projetos_modelar/` (reabrem ao abrir o programa). "MANDAR PARA A MESA 3D" grava o STL em `pecas_modeladas/`.

## Para a IA (MCP `ender-impressora`)
Ferramentas `ender_modelar_*` (14): ajuda, projetos, estado, passo, passos, editar_passo, historico, variavel, ver, ver_4vistas, abrir, exportar, para_mesa. Detalhes em `mcp_ender/MANUAL_MCP.md` (gerado por `python mcp_ender/gerar_manual.py`).
API: `POST /api/modelar {"acao": ...}` (ver `modelar_ui.py`, método `api`).
Fluxo da IA: `ender_modelar_ajuda` → `ender_modelar_passos` → `ender_modelar_ver_4vistas` → corrigir com `ender_modelar_editar_passo` → `ender_modelar_para_mesa`.

## Arquivos
| Arquivo | O que é |
|---|---|
| `modelar.py` | motor: tabela das ferramentas (`OPS`), receita (`Projeto`), seletores de aresta/face, exportar |
| `modelar_ui.py` | a aba (faixa, passos, formulário gerado da tabela `OPS`, vários projetos) e a porta da API |
| `modelar_vista.py` | vista 3D (arestas, clique em face/aresta, prévia, cotas, imagens para a IA) |
| `modelar_esboco.py` | editor de desenho 2D |
| `modelar_tema.py`, `modelar_icones.py` | aparência e ícones (desenhados por código) |
| `testes_modelar/` | `t_motor.py` (55 testes do motor), `t_tela.py` (13, abre janela de teste), `t_api.py` (16, pelo MCP; precisa do programa aberto) |

Para criar uma ferramenta nova: uma entrada em `OPS` (o formulário e a ajuda da IA saem dela) + o cálculo em `_formas` ou `aplicar`.

## Limites conhecidos
- Texto e "face" usam o envelope da peça (em peça curva o texto pode ficar fora da superfície).
- Sem rosca, sem montagem de várias peças com encaixe conferido, sem escultura livre (boneco).
- Vista 3D por software: peça muito pesada (STL com muitos triângulos) aparece simplificada na tela; o arquivo exportado sai inteiro.
- Textos da aba estão só em português (os outros idiomas mostram português nesta aba).

## Arrastar com o mouse (11/11/2026)
Com uma ferramenta aberta (ou um passo clicado na lista), a forma aparece em vermelho e pode ser mexida direto na tela:
- arrastar a forma vermelha = mudar a posição (X/Y; em vista de Frente/Direita, no plano da tela);
- quadradinhos amarelos = tamanho (largura, profundidade, altura, diâmetro);
- bolinha azul = subir/descer (Z);
- **Mover** = arrastar a peça pronta; **Escalar** (em Mais) = puxar o quadradinho do canto;
- o furo desliza na face em que entra. Passo de 0,5 mm (Ctrl = 0,1 mm). Arrastar no vazio continua girando a vista.
As medidas à direita acompanham o mouse; nada muda na peça até clicar APLICAR. Teste: `python testes_modelar/t_arrastar.py`.

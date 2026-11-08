"""Fila de impressao: varios arquivos em sequencia. Entre uma peca e outra o programa PARA e espera o usuário tirar a peca
(botao na tela ou no celular). Avisa no celular (Pushover) ao terminar cada peca, na falha e quando a fila acabar.
Estado guardado em fila.json (sobrevive a fechar o programa)."""
import os, json, time, threading, uuid

PASTA = os.path.dirname(os.path.abspath(__file__))
FILA_JSON = os.path.join(PASTA, 'fila.json')
ESTADOS = {'aguardando': 'na fila', 'imprimindo': 'IMPRIMINDO', 'concluida': 'pronta', 'erro': 'ERRO', 'parada': 'parada', 'pulada': 'pulada'}


class Fila:
    def __init__(self, app):
        self.app = app; self.itens = []; self.estado = 'parada'; self.atual = None; self.msg = ''
        self.auto = False          # continuar sozinho sem esperar tirar a peca (so se as pecas soltam sozinhas)
        self.carregar()

    # ---------- arquivo ----------
    def carregar(self):
        try:
            d = json.load(open(FILA_JSON, encoding='utf-8'))
            self.itens = [i for i in d.get('itens', []) if os.path.isfile(i.get('caminho', ''))]
            self.auto = bool(d.get('auto', False))
            for i in self.itens:
                if i.get('estado') == 'imprimindo': i['estado'] = 'aguardando'     # o programa fechou no meio: volta para a fila
        except Exception: self.itens = []

    def salvar(self):
        try: json.dump(dict(itens=self.itens, auto=self.auto), open(FILA_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        except Exception: pass

    # ---------- editar ----------
    def adicionar(self, caminho, preset=None, copias=1):
        for _ in range(max(1, int(copias))):
            self.itens.append(dict(id=uuid.uuid4().hex[:8], caminho=caminho, nome=os.path.basename(caminho), preset=preset, estado='aguardando', resultado='', hora=''))
        self.salvar()

    def remover(self, id_):
        self.itens = [i for i in self.itens if i['id'] != id_ or i['estado'] == 'imprimindo']; self.salvar()

    def mover(self, id_, delta):
        ids = [i['id'] for i in self.itens]
        if id_ not in ids: return
        k = ids.index(id_); j = k + delta
        if 0 <= j < len(self.itens): self.itens[k], self.itens[j] = self.itens[j], self.itens[k]; self.salvar()

    def limpar_prontas(self):
        self.itens = [i for i in self.itens if i['estado'] in ('aguardando', 'imprimindo')]; self.salvar()

    def limpar(self):
        self.itens = [i for i in self.itens if i['estado'] == 'imprimindo']; self.estado = 'parada'; self.salvar()

    def reativar(self, id_):
        for i in self.itens:
            if i['id'] == id_ and i['estado'] != 'imprimindo': i['estado'] = 'aguardando'; i['resultado'] = ''
        self.salvar()

    def pendentes(self): return [i for i in self.itens if i['estado'] == 'aguardando']

    # ---------- andamento ----------
    def iniciar(self):
        """Botao COMECAR A FILA."""
        if self.app.ocupado: return {'ok': False, 'erro': 'a impressora esta ocupada'}
        if not self.pendentes(): return {'ok': False, 'erro': 'a fila esta vazia'}
        self.estado = 'rodando'; return self.proximo()

    def proximo(self):
        p = self.pendentes()
        if not p:
            self.estado = 'parada'; self.atual = None; self.msg = 'Fila terminada.'; self.salvar()
            self.app.avisar('Fila de impressão terminada: todas as peças foram impressas.', 'terminou'); return {'ok': True, 'fim': True}
        it = p[0]; it['estado'] = 'imprimindo'; it['hora'] = time.strftime('%H:%M'); self.atual = it['id']; self.estado = 'rodando'; self.salvar()
        self.msg = 'Preparando %s...' % it['nome']
        def run():
            try:
                if it.get('preset'):
                    try: self.app.preset.set(it['preset'])
                    except Exception: pass
                r = self.app.carregar(it['caminho'])
                if not r.get('ok'): raise RuntimeError(r.get('erro', 'nao preparou'))
                r = self.app.iniciar_impressao('fila')
                if not r.get('ok'): raise RuntimeError(r.get('erro', 'nao comecou'))
                self.msg = 'Imprimindo %s' % it['nome']
            except Exception as e:
                it['estado'] = 'erro'; it['resultado'] = str(e)[:160]; self.estado = 'parada'; self.atual = None; self.salvar()
                self.msg = 'Fila parada: %s' % str(e)[:120]; self.app.say('Fila: ' + self.msg)
                self.app.avisar('Fila parada em %s: %s' % (it['nome'], str(e)[:140]), 'erro')
        threading.Thread(target=run, daemon=True).start()
        return {'ok': True}

    def ao_terminar(self, resultado):
        """Chamado pelo programa quando uma impressao acaba (concluida / parada / erro: texto)."""
        if self.estado != 'rodando' or not self.atual: return
        it = next((i for i in self.itens if i['id'] == self.atual), None)
        if not it: return
        it['hora'] = time.strftime('%H:%M')
        if resultado == 'concluida':
            it['estado'] = 'concluida'; it['resultado'] = 'ok'; self.atual = None; self.salvar()
            if not self.pendentes():
                self.estado = 'parada'; self.msg = 'Fila terminada: %s foi a ultima.' % it['nome']
                self.app.avisar('Impressão de %s concluída. A FILA TERMINOU, não tem mais peças.' % it['nome'], 'terminou'); return
            if self.auto:
                self.msg = '%s pronta; continuando sozinho...' % it['nome']
                self.app.avisar('%s pronta. Próxima peça começando sozinha (%d na fila).' % (it['nome'], len(self.pendentes())), 'terminou')
                threading.Timer(3, self.proximo).start()
            else:
                self.estado = 'esperando_tirar'; self.msg = 'TIRE A PEÇA DA MESA e toque em CONTINUAR (faltam %d).' % len(self.pendentes())
                self.app.avisar('%s pronta! TIRE A PEÇA da mesa e toque em "Tirei a peça, continuar" (faltam %d).' % (it['nome'], len(self.pendentes())), 'tirar_peca', prioridade=1)
        else:
            it['estado'] = 'erro' if resultado.startswith('erro') else 'parada'; it['resultado'] = resultado[:160]; self.estado = 'parada'; self.atual = None; self.salvar()
            self.msg = 'Fila PARADA em %s (%s). Arrume e toque em COMEÇAR para seguir.' % (it['nome'], resultado[:80])
            self.app.avisar('FILA PARADA em %s: %s. Faltam %d peça(s); arrume e toque em COMEÇAR A FILA.' % (it['nome'], resultado[:100], len(self.pendentes())), 'erro', prioridade=1)

    def continuar(self):
        """Botao 'Tirei a peca, continuar' (tela ou celular)."""
        if self.estado != 'esperando_tirar': return {'ok': False, 'erro': 'a fila nao esta esperando'}
        if self.app.ocupado: return {'ok': False, 'erro': 'a impressora ainda esta ocupada'}
        return self.proximo()

    def pular(self):
        p = self.pendentes()
        if not p: return {'ok': False, 'erro': 'nada para pular'}
        p[0]['estado'] = 'pulada'; self.salvar()
        if self.estado == 'esperando_tirar' and not self.pendentes(): self.estado = 'parada'; self.msg = 'Fila terminada.'
        return {'ok': True}

    def parar(self):
        self.estado = 'parada'; self.msg = 'Fila parada (a impressao atual continua ate o fim).'; self.salvar(); return {'ok': True}

    def status(self):
        return dict(estado=self.estado, msg=self.msg, auto=self.auto, atual=self.atual, pendentes=len(self.pendentes()),
                    itens=[dict(id=i['id'], nome=i['nome'], estado=i['estado'], estado_txt=ESTADOS.get(i['estado'], i['estado']), resultado=i.get('resultado', ''), hora=i.get('hora', '')) for i in self.itens])

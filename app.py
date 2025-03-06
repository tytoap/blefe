from flask import Flask, render_template_string, request, redirect, url_for, session
from flask_session import Session
from flask_socketio import SocketIO, emit, join_room
import uuid
import json
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua-chave-secreta-aqui'  # Substitua por uma chave segura
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)
socketio = SocketIO(app)

# Arquivo para armazenar jogadores
JOGADORES_FILE = "jogadores.json"

# Estado global das salas
salas = {}  # {sala_id: {'jogadores': {}, 'escolhas': {}, 'pontuacao': {}, 'rodada_atual': 0, 'historico': [], 'nomes_internos': {}, 'ultimo_resultado': ''}}
jogadores_conectados = {}  # {nome_jogador: {'sid': id_sessao, 'sala': sala_id}}

# Função para carregar jogadores do JSON
def carregar_jogadores():
    if os.path.exists(JOGADORES_FILE):
        with open(JOGADORES_FILE, 'r') as f:
            return json.load(f)
    return []

# Função para salvar jogadores no JSON
def salvar_jogadores(jogadores):
    with open(JOGADORES_FILE, 'w') as f:
        json.dump(jogadores, f)

# Middleware para verificar sessão
def login_required(f):
    def wrap(*args, **kwargs):
        if 'nome' not in session:
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# Tela inicial (login)
HOME_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Jogo do Blefe - Bem-vindo</title>
    <style>
        body { font-family: 'Roboto Mono', monospace; background: linear-gradient(135deg, #1a1a2e, #16213e); color: #e0e0e0; text-align: center; padding: 50px; margin: 0; }
        h1 { color: #ff6f61; text-shadow: 2px 2px 4px #000; font-size: 2.5em; margin-bottom: 20px; }
        .container { max-width: 600px; margin: 0 auto; background: rgba(0, 0, 0, 0.8); padding: 30px; border-radius: 15px; border: 3px solid #ff6f61; box-shadow: 0 0 20px rgba(255, 111, 97, 0.5); }
        input { padding: 10px; font-size: 1em; border: 2px solid #ff6f61; border-radius: 5px; background: #fff; color: #333; margin: 10px 0; }
        button { padding: 12px 25px; background: #ff6f61; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 1em; text-transform: uppercase; transition: transform 0.2s, background 0.2s; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
        button:hover { background: #ff3d2e; transform: scale(1.05); }
        .intro { color: #ffd700; font-size: 1em; margin: 20px 0; text-shadow: 1px 1px 2px #000; }
        #mensagem { color: #ffd700; font-size: 1.2em; margin-top: 20px; }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Roboto+Mono&display=swap" rel="stylesheet">
</head>
<body>
    <div class="container">
        <h1>Jogo do Blefe</h1>
        <div class="intro">
            <p>Bem-vindo ao Jogo do Blefe! Engane seu adversário e acumule pontos em 5 rodadas de pura estratégia.</p>
        </div>
        <label>Seu Nome:</label>
        <input type="text" id="nome" maxlength="20">
        <button onclick="entrar()">Entrar</button>
        <div id="mensagem"></div>
    </div>

    <script>
        function entrar() {
            const nome = document.getElementById('nome').value.trim();
            if (!nome) {
                document.getElementById('mensagem').innerText = 'Digite um nome!';
                return;
            }
            fetch('/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nome: nome })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.href = '/lobby';
                } else {
                    document.getElementById('mensagem').innerText = data.error;
                }
            });
        }
    </script>
</body>
</html>
"""

# Tela de lobby
LOBBY_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Jogo do Blefe - Lobby</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.js"></script>
    <style>
        body { font-family: 'Roboto Mono', monospace; background: linear-gradient(135deg, #1a1a2e, #16213e); color: #e0e0e0; padding: 50px; margin: 0; }
        h1 { color: #ff6f61; text-shadow: 2px 2px 4px #000; font-size: 2em; margin-bottom: 20px; }
        .container { max-width: 600px; margin: 0 auto; background: rgba(0, 0, 0, 0.8); padding: 30px; border-radius: 15px; border: 3px solid #ff6f61; box-shadow: 0 0 20px rgba(255, 111, 97, 0.5); }
        .player-info { position: absolute; top: 10px; left: 10px; color: #00ccff; font-size: 1em; text-shadow: 1px 1px 2px #000; }
        button { padding: 12px 25px; background: #ff6f61; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 1em; text-transform: uppercase; transition: transform 0.2s, background 0.2s; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
        button:hover { background: #ff3d2e; transform: scale(1.05); }
        #salas { margin-top: 20px; }
        .sala-item { background: rgba(255, 255, 255, 0.1); padding: 10px; margin: 10px 0; border-radius: 5px; border: 1px solid #00ccff; }
        #aviso { color: #ff3d2e; font-size: 1.2em; margin-top: 20px; }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Roboto+Mono&display=swap" rel="stylesheet">
</head>
<body>
    <div class="player-info">Jogador: {{ nome }}</div>
    <div class="container">
        <h1>Jogo do Blefe - Lobby</h1>
        <button onclick="criarSala()">Criar Sala</button>
        <div id="salas"></div>
        <div id="aviso"></div>
    </div>

    <script>
        const socket = io();
        const meuNome = "{{ nome }}";

        socket.on('connect', () => {
            console.log('Conectado ao servidor');
            socket.emit('registrar_lobby', { nome: meuNome });
        });

        socket.on('atualizar_salas', (data) => {
            console.log('Salas recebidas:', data);
            const salasDiv = document.getElementById('salas');
            salasDiv.innerHTML = '<h3>Salas Disponíveis:</h3>';
            data.salas.forEach(sala => {
                const salaDiv = document.createElement('div');
                salaDiv.className = 'sala-item';
                salaDiv.innerHTML = `Sala ${sala.id} - Jogadores: ${sala.jogadores.length}/2 <button onclick="entrarSala('${sala.id}')">Entrar</button>`;
                salasDiv.appendChild(salaDiv);
            });
        });

        socket.on('mensagem', (data) => {
            console.log('Mensagem recebida:', data);
            if (data.error) {
                document.getElementById('aviso').innerText = data.error;
                setTimeout(() => document.getElementById('aviso').innerText = '', 3000); // Remove após 3 segundos
            }
        });

        function criarSala() {
            socket.emit('criar_sala', { nome: meuNome });
        }

        function entrarSala(salaId) {
            socket.emit('entrar_sala', { nome: meuNome, sala: salaId });
        }

        socket.on('redirecionar', (data) => {
            window.location.href = data.url;
        });
    </script>
</body>
</html>
"""

# Tela do jogo
GAME_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Jogo do Blefe - Sala {{ sala_id }}</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.js"></script>
    <style>
        body { font-family: 'Roboto Mono', monospace; background: linear-gradient(135deg, #1a1a2e, #16213e); color: #e0e0e0; padding: 20px; margin: 0; overflow: auto; }
        h1 { color: #ff6f61; text-shadow: 2px 2px 4px #000; font-size: 2em; margin-bottom: 20px; }
        .container { max-width: 800px; margin: 0 auto; background: rgba(0, 0, 0, 0.8); padding: 20px; border-radius: 15px; border: 3px solid #ff6f61; box-shadow: 0 0 20px rgba(255, 111, 97, 0.5); }
        .player-info { position: absolute; top: 10px; left: 10px; color: #00ccff; font-size: 1em; text-shadow: 1px 1px 2px #000; }
        .game-controls, .rules { margin: 20px 0; }
        button { padding: 12px 25px; margin: 5px; background: #ff6f61; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 1em; text-transform: uppercase; transition: transform 0.2s, background 0.2s; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3); }
        button:hover { background: #ff3d2e; transform: scale(1.05); }
        button:disabled { background: #666; cursor: not-allowed; transform: none; }
        #mensagem { color: #ffd700; font-size: 1.2em; margin: 15px 0; text-shadow: 1px 1px 2px #000; }
        .score-container { display: flex; justify-content: center; gap: 20px; margin: 20px 0; }
        .score-card { background: rgba(255, 255, 255, 0.1); border: 2px solid #00ccff; border-radius: 10px; padding: 15px; width: 200px; text-align: center; box-shadow: 0 0 10px rgba(0, 204, 255, 0.5); }
        .score-card h3 { color: #00ccff; font-size: 1em; margin: 0 0 10px 0; text-shadow: 1px 1px 2px #000; }
        .score-card span { color: #fff; font-size: 1.2em; }
        #rodada { font-size: 1.1em; color: #fff; }
        #resultado, #historico { background: rgba(255, 255, 255, 0.1); padding: 15px; border-radius: 10px; margin-top: 20px; border: 1px solid #ff6f61; color: #e0e0e0; font-size: 1em; }
        #historico { text-align: left; max-height: 200px; overflow-y: auto; }
        .rules { background: rgba(255, 255, 255, 0.05); padding: 15px; border-radius: 10px; border: 1px solid #ffd700; color: #ffd700; font-size: 0.9em; text-align: left; margin-top: 20px; }
        .rules h2 { color: #ffd700; font-size: 1.2em; margin-bottom: 10px; }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Roboto+Mono&display=swap" rel="stylesheet">
</head>
<body>
    <div class="player-info">Jogador: {{ nome }}</div>
    <div class="container">
        <h1>Jogo do Blefe - Sala {{ sala_id }}</h1>
        <div class="game-controls">
            <button id="confiar" onclick="escolher('Confiar')" disabled>Confiar</button>
            <button id="blefar" onclick="escolher('Blefar')" disabled>Blefar</button>
            <button id="nova-rodada" onclick="novaRodada()" disabled>Nova Rodada</button>
        </div>
        <div id="mensagem"></div>
        <div class="score-container">
            <div class="score-card">
                <h3>Meus Pontos</h3>
                <span id="meus-pontos">0</span>
            </div>
            <div class="score-card">
                <h3>Pontos do Adversário</h3>
                <span id="pontos-adversario">0</span>
            </div>
        </div>
        <div id="rodada">Rodada: <span id="rodada-atual">0</span> / 5</div>
        <div id="resultado"></div>
        <div id="historico"><strong>Histórico:</strong></div>
        <div class="rules">
            <h2>Regras do Jogo</h2>
            <p>Neste jogo de blefe, você enfrenta um adversário tentando acumular mais pontos em 5 rodadas. Escolha entre <strong>Confiar</strong> ou <strong>Blefar</strong>:</p>
            <ul>
                <li>Se ambos <strong>confiarem</strong>, cada um ganha 2 pontos.</li>
                <li>Se um <strong>blefa</strong> e o outro <strong>confia</strong>, o blefador ganha 5 pontos e o confiante ganha 0.</li>
                <li>Se ambos <strong>blefarem</strong>, cada um ganha 1 ponto.</li>
            </ul>
            <p>O objetivo é superar seu adversário em pontos. Use sua estratégia para enganá-lo e vencer!</p>
        </div>
    </div>

    <script>
        const socket = io();
        let meuJogador = "{{ nome }}";
        let meuInterno = null;
        const salaId = "{{ sala_id }}";

        socket.on('connect', () => {
            console.log('Conectado ao servidor');
            socket.emit('entrar_sala', { nome: meuJogador, sala: salaId });
        });

        socket.on('mensagem', (data) => {
            console.log('Mensagem recebida:', data);
            document.getElementById('mensagem').innerText = data.status || data.error;
            if (data.registrado === true) {
                console.log('Registro bem-sucedido, habilitando botões');
                meuInterno = data.interno;
                document.getElementById('confiar').disabled = false;
                document.getElementById('blefar').disabled = false;
            }
        });

        socket.on('atualizar_estado', (data) => {
            console.log('Estado recebido:', data);

            if (meuInterno === 'j1') {
                document.getElementById('meus-pontos').innerText = data.pontuacao.j1 || 0;
                document.getElementById('pontos-adversario').innerText = data.pontuacao.j2 || 0;
            } else if (meuInterno === 'j2') {
                document.getElementById('meus-pontos').innerText = data.pontuacao.j2 || 0;
                document.getElementById('pontos-adversario').innerText = data.pontuacao.j1 || 0;
            } else {
                document.getElementById('meus-pontos').innerText = 0;
                document.getElementById('pontos-adversario').innerText = 0;
            }

            document.getElementById('rodada-atual').innerText = data.rodada_atual;
            document.getElementById('resultado').innerText = data.resultado || '';
            const historicoDiv = document.getElementById('historico');
            historicoDiv.innerHTML = '<strong>Histórico:</strong><br>' + 
                (data.historico.length ? data.historico.join('<br>') : 'Nenhum resultado ainda');

            console.log('Rodada atual:', data.rodada_atual, 'Escolhas:', data.escolhas);
            if (data.rodada_atual < 5) {
                if (!data.escolhas.j1 || !data.escolhas.j2) {
                    document.getElementById('confiar').disabled = false;
                    document.getElementById('blefar').disabled = false;
                    document.getElementById('nova-rodada').disabled = true;
                } else {
                    document.getElementById('confiar').disabled = true;
                    document.getElementById('blefar').disabled = true;
                    document.getElementById('nova-rodada').disabled = false;
                }
            } else if (data.rodada_atual === 5 && (!data.escolhas.j1 || !data.escolhas.j2)) {
                document.getElementById('confiar').disabled = true;
                document.getElementById('blefar').disabled = true;
                document.getElementById('nova-rodada').disabled = false;
                document.getElementById('mensagem').innerText = data.vencedor || 'Jogo terminado!';
            } else {
                document.getElementById('confiar').disabled = true;
                document.getElementById('blefar').disabled = true;
                document.getElementById('nova-rodada').disabled = true;
            }
        });

        function escolher(escolha) {
            if (!meuJogador) {
                alert('Erro: jogador não identificado!');
                return;
            }
            console.log('Escolha feita:', escolha);
            document.getElementById('confiar').disabled = true;
            document.getElementById('blefar').disabled = true;
            socket.emit('escolher', { jogador: meuJogador, escolha: escolha, sala: salaId });
        }

        function novaRodada() {
            console.log('Iniciando nova rodada');
            socket.emit('nova_rodada', { sala: salaId });
        }
    </script>
</body>
</html>
"""

# Rotas do Flask
@app.route('/')
def home():
    if 'nome' in session:
        return redirect(url_for('lobby'))
    return render_template_string(HOME_TEMPLATE)

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    nome = data.get('nome')
    jogadores = carregar_jogadores()

    if nome in jogadores:
        return {"success": False, "error": "Nome já em uso"}
    jogadores.append(nome)
    salvar_jogadores(jogadores)
    session['nome'] = nome
    return {"success": True}

@app.route('/lobby')
@login_required
def lobby():
    return render_template_string(LOBBY_TEMPLATE, nome=session['nome'])

@app.route('/jogo/<sala_id>')
@login_required
def jogo(sala_id):
    nome = session['nome']
    if sala_id not in salas:
        return redirect(url_for('lobby'))  # Volta ao lobby se a sala não existe
    if len(salas[sala_id]['jogadores']) >= 2 and nome not in salas[sala_id]['jogadores']:
        # Não retorna erro, apenas redireciona para o lobby (aviso será enviado via SocketIO)
        return redirect(url_for('lobby'))
    if nome not in jogadores_conectados:
        jogadores_conectados[nome] = {'sid': None, 'sala': None}
    return render_template_string(GAME_TEMPLATE, nome=nome, sala_id=sala_id)

# Lógica do SocketIO
def atualizar_salas():
    salas_info = [{'id': sala_id, 'jogadores': list(sala['jogadores'].keys())} for sala_id, sala in salas.items()]
    emit('atualizar_salas', {'salas': salas_info}, broadcast=True)

def atualizar_estado(sala_id):
    sala = salas[sala_id]
    nome_j1 = sala['nomes_internos']['j1'] if sala['nomes_internos']['j1'] else 'J1'
    nome_j2 = sala['nomes_internos']['j2'] if sala['nomes_internos']['j2'] else 'J2'
    
    if sala['escolhas']['j1'] and sala['escolhas']['j2']:
        numero_rodada = sala['rodada_atual'] + 1 if sala['ultimo_resultado'] == "" else sala['rodada_atual']
        sala['ultimo_resultado'] = f"Rodada {numero_rodada}: {nome_j1} ({sala['escolhas']['j1']}) vs {nome_j2} ({sala['escolhas']['j2']})"
    
    resultado = sala['ultimo_resultado'] if sala['ultimo_resultado'] else (
        f"Rodada {sala['rodada_atual'] + 1}: {nome_j1} ({sala['escolhas']['j1'] or '?'}) vs {nome_j2} ({sala['escolhas']['j2'] or '?'})"
    ) if sala['rodada_atual'] < 5 else sala['ultimo_resultado']

    estado = {
        'pontuacao': sala['pontuacao'],
        'rodada_atual': sala['rodada_atual'],
        'historico': sala['historico'],
        'resultado': resultado,
        'escolhas': sala['escolhas'],
        'nomes': sala['nomes_internos']
    }
    if sala['rodada_atual'] >= 5:
        vencedor = nome_j1 if sala['pontuacao']['j1'] > sala['pontuacao']['j2'] else nome_j2 if sala['pontuacao']['j2'] > sala['pontuacao']['j1'] else "Empate"
        estado['vencedor'] = f"Jogo terminado! Vencedor: {vencedor}"
    
    print(f"Estado enviado para sala {sala_id} - Rodada: {sala['rodada_atual']}, Pontuação: {sala['pontuacao']}")
    emit('atualizar_estado', estado, room=sala_id)

@socketio.on('connect')
def handle_connect():
    if 'nome' in session and session['nome'] not in jogadores_conectados:
        jogadores_conectados[session['nome']] = {'sid': request.sid, 'sala': None}
        print(f"Jogador {session['nome']} conectado")

@socketio.on('registrar_lobby')
def handle_registrar_lobby(data):
    nome_jogador = data['nome']
    if nome_jogador != session.get('nome'):
        emit('mensagem', {'error': 'Sessão inválida'}, room=request.sid)
        return
    if nome_jogador not in jogadores_conectados:
        jogadores_conectados[nome_jogador] = {'sid': request.sid, 'sala': None}
    print(f"Jogador {nome_jogador} registrado no lobby")
    atualizar_salas()

@socketio.on('criar_sala')
def handle_criar_sala(data):
    nome_jogador = data['nome']
    if nome_jogador != session.get('nome'):
        emit('mensagem', {'error': 'Sessão inválida'}, room=request.sid)
        return
    sala_id = str(uuid.uuid4())[:8]
    salas[sala_id] = {
        'jogadores': {},
        'escolhas': {'j1': None, 'j2': None},
        'pontuacao': {'j1': 0, 'j2': 0},
        'rodada_atual': 0,
        'historico': [],
        'nomes_internos': {'j1': None, 'j2': None},
        'ultimo_resultado': ''
    }
    emit('mensagem', {'status': f'Sala {sala_id} criada! Redirecionando...'}, room=request.sid)
    socketio.emit('redirecionar', {'url': f'/jogo/{sala_id}'}, room=request.sid)
    atualizar_salas()

@socketio.on('entrar_sala')
def handle_entrar_sala(data):
    nome_jogador = data['nome']
    sala_id = data['sala']
    if nome_jogador != session.get('nome'):
        emit('mensagem', {'error': 'Sessão inválida'}, room=request.sid)
        return
    if sala_id not in salas:
        emit('mensagem', {'error': 'Sala não encontrada'}, room=request.sid)
        return
    if nome_jogador not in jogadores_conectados:
        jogadores_conectados[nome_jogador] = {'sid': request.sid, 'sala': None}
    sala = salas[sala_id]
    if len(sala['jogadores']) >= 2:
        emit('mensagem', {'error': 'Sala cheia! Escolha outra sala ou crie uma nova.'}, room=request.sid)
        return
    
    join_room(sala_id)
    interno = 'j1' if not sala['nomes_internos']['j1'] else 'j2'
    sala['jogadores'][nome_jogador] = request.sid
    sala['nomes_internos'][interno] = nome_jogador
    jogadores_conectados[nome_jogador]['sala'] = sala_id
    jogadores_conectados[nome_jogador]['sid'] = request.sid
    emit('mensagem', {'status': f'Você entrou na sala {sala_id} como {interno}', 'registrado': True, 'interno': interno}, room=request.sid)
    print(f"Jogador {nome_jogador} entrou na sala {sala_id} como {interno}")
    socketio.emit('redirecionar', {'url': f'/jogo/{sala_id}'}, room=request.sid)
    atualizar_estado(sala_id)
    atualizar_salas()

@socketio.on('escolher')
def handle_escolher(data):
    nome_jogador = data['jogador']
    escolha = data['escolha']
    sala_id = data['sala']
    if nome_jogador != session.get('nome'):
        emit('mensagem', {'error': 'Sessão inválida'}, room=request.sid)
        return
    if sala_id not in salas:
        emit('mensagem', {'error': 'Sala não encontrada'}, room=request.sid)
        return
    sala = salas[sala_id]
    if nome_jogador not in sala['jogadores']:
        emit('mensagem', {'error': 'Você não está nesta sala'}, room=request.sid)
        return
    if escolha not in ["Confiar", "Blefar"]:
        emit('mensagem', {'error': 'Escolha inválida'}, room=request.sid)
        return
    
    interno = 'j1' if sala['nomes_internos']['j1'] == nome_jogador else 'j2'
    sala['escolhas'][interno] = escolha
    emit('mensagem', {'status': 'Escolha registrada, aguardando o outro jogador'}, room=request.sid)
    atualizar_estado(sala_id)

    if sala['escolhas']['j1'] and sala['escolhas']['j2']:
        resultado = calcular_resultado(sala['escolhas']['j1'], sala['escolhas']['j2'])
        sala['pontuacao']['j1'] += resultado['j1']
        sala['pontuacao']['j2'] += resultado['j2']
        sala['rodada_atual'] += 1
        nome_j1 = sala['nomes_internos']['j1']
        nome_j2 = sala['nomes_internos']['j2']
        sala['historico'].append(f"Rodada {sala['rodada_atual']}: {nome_j1} ({sala['escolhas']['j1']}) vs {nome_j2} ({sala['escolhas']['j2']}) = {nome_j1}: {resultado['j1']}, {nome_j2}: {resultado['j2']}")
        sala['escolhas']['j1'] = None
        sala['escolhas']['j2'] = None
        atualizar_estado(sala_id)

@socketio.on('nova_rodada')
def handle_nova_rodada(data):
    sala_id = data['sala']
    if sala_id not in salas:
        emit('mensagem', {'error': 'Sala não encontrada'}, room=request.sid)
        return
    sala = salas[sala_id]
    if len(sala['jogadores']) != 2:
        emit('mensagem', {'error': 'Não é possível iniciar uma nova rodada sem dois jogadores'}, room=request.sid)
        return
    
    if sala['rodada_atual'] >= 5:
        sala['rodada_atual'] = 0
        sala['pontuacao']['j1'] = 0
        sala['pontuacao']['j2'] = 0
        sala['historico'].clear()
    sala['ultimo_resultado'] = ""
    sala['escolhas']['j1'] = None
    sala['escolhas']['j2'] = None
    emit('mensagem', {'status': 'Nova rodada iniciada! Faça sua escolha'}, room=sala_id)
    atualizar_estado(sala_id)

@socketio.on('disconnect')
def handle_disconnect():
    nome_jogador = next((nome for nome, info in jogadores_conectados.items() if info['sid'] == request.sid), None)
    if nome_jogador:
        sala_id = jogadores_conectados[nome_jogador]['sala']
        if sala_id and sala_id in salas:
            sala = salas[sala_id]
            if nome_jogador in sala['jogadores']:
                del sala['jogadores'][nome_jogador]
                interno = 'j1' if sala['nomes_internos']['j1'] == nome_jogador else 'j2'
                sala['nomes_internos'][interno] = None
                sala['escolhas'][interno] = None
                if not sala['jogadores']:
                    del salas[sala_id]
                else:
                    atualizar_estado(sala_id)
            print(f"Jogador {nome_jogador} desconectou-se da sala {sala_id}")
        del jogadores_conectados[nome_jogador]
        atualizar_salas()

def calcular_resultado(escolha_j1, escolha_j2):
    if escolha_j1 == "Confiar" and escolha_j2 == "Confiar":
        return {"j1": 2, "j2": 2}
    elif escolha_j1 == "Confiar" and escolha_j2 == "Blefar":
        return {"j1": 0, "j2": 5}
    elif escolha_j1 == "Blefar" and escolha_j2 == "Confiar":
        return {"j1": 5, "j2": 0}
    elif escolha_j1 == "Blefar" and escolha_j2 == "Blefar":
        return {"j1": 1, "j2": 1}
    return {"error": "Escolhas inválidas"}

if __name__ == "__main__":
    salvar_jogadores([])
    socketio.run(app, debug=True)

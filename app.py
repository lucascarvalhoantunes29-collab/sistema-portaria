from flask import Flask, render_template, request, redirect, session, send_file
from database import conectar, criar_tabelas
from datetime import datetime, timezone, timedelta
from functools import wraps
from psycopg.errors import ForeignKeyViolation
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import io
import base64
import secrets
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
criar_tabelas()

USUARIO = os.getenv('USUARIO')
SENHA = os.getenv('SENHA')

# ── FUSO HORÁRIO ─────────────────────────────────
BR_TZ = timezone(timedelta(hours=-3))

def agora():
    return datetime.now(BR_TZ).strftime('%d/%m/%Y %H:%M')

# ── FOTO ─────────────────────────────────────────
FOTO_MIME_PERMITIDOS = {'image/jpeg', 'image/png', 'image/webp'}
FOTO_EXTENSOES_PERMITIDAS = {'jpg', 'jpeg', 'png', 'webp'}
FOTO_MAX_BYTES = 8 * 1024 * 1024  # 8 MB

def validar_foto(arquivo):
    """Valida o arquivo enviado. Retorna (bytes, mime) ou lança ValueError."""
    nome = arquivo.filename.lower()
    ext = nome.rsplit('.', 1)[-1] if '.' in nome else ''
    if ext not in FOTO_EXTENSOES_PERMITIDAS:
        raise ValueError('Formato não suportado. Use JPG, PNG ou WEBP.')
    dados = arquivo.read()
    if len(dados) > FOTO_MAX_BYTES:
        raise ValueError('A foto deve ter no máximo 8 MB.')
    mime = arquivo.mimetype
    if mime not in FOTO_MIME_PERMITIDOS:
        mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                'png': 'image/png', 'webp': 'image/webp'}.get(ext, 'image/jpeg')
    return dados, mime

# ── AUTH ─────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logado'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ── INDEX ─────────────────────────────────────────
@app.route('/')
@login_required
def index():
    conn = conectar()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM moradores')
    total_moradores = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM visitantes')
    total_visitantes = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM veiculos')
    total_veiculos = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM vagas WHERE veiculo_id IS NOT NULL')
    vagas_ocupadas = cur.fetchone()[0]
    conn.close()
    return render_template('index.html',
        total_moradores=total_moradores,
        total_visitantes=total_visitantes,
        total_veiculos=total_veiculos,
        vagas_ocupadas=vagas_ocupadas)

# ── BLOCOS ───────────────────────────────────────
@app.route('/blocos')
@login_required
def listar_blocos():
    conn = conectar()
    cur = conn.cursor()
    cur.execute('SELECT * FROM blocos ORDER BY nome')
    blocos = cur.fetchall()
    conn.close()
    return render_template('blocos/listar.html', blocos=blocos)

@app.route('/blocos/novo', methods=['GET', 'POST'])
@login_required
def novo_bloco():
    if request.method == 'POST':
        conn = conectar()
        cur = conn.cursor()
        cur.execute('INSERT INTO blocos (nome) VALUES (%s)', (request.form['nome'],))
        conn.commit()
        conn.close()
        return redirect('/blocos')
    return render_template('blocos/form.html', bloco=None)

@app.route('/blocos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_bloco(id):
    conn = conectar()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute('UPDATE blocos SET nome=%s WHERE id=%s', (request.form['nome'], id))
        conn.commit()
        conn.close()
        return redirect('/blocos')
    cur.execute('SELECT * FROM blocos WHERE id=%s', (id,))
    bloco = cur.fetchone()
    conn.close()
    return render_template('blocos/form.html', bloco=bloco)

@app.route('/blocos/excluir/<int:id>')
@login_required
def excluir_bloco(id):
    conn = conectar()
    cur = conn.cursor()
    try:
        cur.execute('DELETE FROM blocos WHERE id=%s', (id,))
        conn.commit()
    except ForeignKeyViolation:
        conn.rollback()
        conn.close()
        return "Não é possível excluir: existem dados vinculados a esse bloco"
    conn.close()
    return redirect('/blocos')

# ── APARTAMENTOS ─────────────────────────────────
@app.route('/apartamentos')
@login_required
def listar_apartamentos():
    conn = conectar()
    cur = conn.cursor()
    cur.execute('''
        SELECT a.id, a.numero, b.nome, b.id
        FROM apartamentos a
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    apartamentos = cur.fetchall()
    conn.close()
    return render_template('apartamentos/listar.html', apartamentos=apartamentos)

@app.route('/apartamentos/novo', methods=['GET', 'POST'])
@login_required
def novo_apartamento():
    conn = conectar()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute('INSERT INTO apartamentos (numero, bloco_id) VALUES (%s, %s)',
                    (request.form['numero'], request.form['bloco_id']))
        conn.commit()
        conn.close()
        return redirect('/apartamentos')
    cur.execute('SELECT * FROM blocos ORDER BY nome')
    blocos = cur.fetchall()
    conn.close()
    return render_template('apartamentos/form.html', apartamento=None, blocos=blocos)

@app.route('/apartamentos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_apartamento(id):
    conn = conectar()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute('UPDATE apartamentos SET numero=%s, bloco_id=%s WHERE id=%s',
                    (request.form['numero'], request.form['bloco_id'], id))
        conn.commit()
        conn.close()
        return redirect('/apartamentos')
    cur.execute('''
        SELECT a.id, a.numero, b.nome, b.id
        FROM apartamentos a
        JOIN blocos b ON a.bloco_id = b.id
        WHERE a.id=%s
    ''', (id,))
    apartamento = cur.fetchone()
    cur.execute('SELECT * FROM blocos ORDER BY nome')
    blocos = cur.fetchall()
    conn.close()
    return render_template('apartamentos/form.html', apartamento=apartamento, blocos=blocos)

@app.route('/apartamentos/excluir/<int:id>')
@login_required
def excluir_apartamento(id):
    conn = conectar()
    cur = conn.cursor()
    try:
        cur.execute('DELETE FROM apartamentos WHERE id=%s', (id,))
        conn.commit()
    except ForeignKeyViolation:
        conn.rollback()
        conn.close()
        return "Não é possível excluir: existem moradores nesse apartamento"
    conn.close()
    return redirect('/apartamentos')

# ── MORADORES ────────────────────────────────────
@app.route('/moradores')
@login_required
def listar_moradores():
    conn = conectar()
    cur = conn.cursor()
    cur.execute('''
        SELECT m.id, m.nome, m.telefone, m.email, a.numero, b.nome, b.id, a.id
        FROM moradores m
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    moradores = cur.fetchall()
    conn.close()
    return render_template('moradores/listar.html', moradores=moradores)

@app.route('/moradores/novo', methods=['GET', 'POST'])
@login_required
def novo_morador():
    conn = conectar()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute('INSERT INTO moradores (nome, telefone, email, apartamento_id) VALUES (%s,%s,%s,%s)',
                    (request.form['nome'], request.form['telefone'],
                     request.form['email'], request.form['apartamento_id']))
        conn.commit()
        conn.close()
        return redirect('/moradores')
    cur.execute('SELECT * FROM blocos ORDER BY nome')
    blocos = cur.fetchall()
    cur.execute('''
        SELECT a.id, a.numero, b.nome
        FROM apartamentos a
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    apartamentos = cur.fetchall()
    conn.close()
    return render_template('moradores/form.html', morador=None, blocos=blocos, apartamentos=apartamentos)

@app.route('/moradores/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_morador(id):
    conn = conectar()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute('''
            UPDATE moradores SET nome=%s, telefone=%s, email=%s, apartamento_id=%s WHERE id=%s
        ''', (request.form['nome'], request.form['telefone'],
              request.form['email'], request.form['apartamento_id'], id))
        conn.commit()
        conn.close()
        return redirect('/moradores')
    cur.execute('''
        SELECT m.id, m.nome, m.telefone, m.email, a.numero, b.nome, b.id, a.id
        FROM moradores m
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        WHERE m.id=%s
    ''', (id,))
    morador = cur.fetchone()
    cur.execute('SELECT * FROM blocos ORDER BY nome')
    blocos = cur.fetchall()
    cur.execute('''
        SELECT a.id, a.numero, b.nome
        FROM apartamentos a
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    apartamentos = cur.fetchall()
    conn.close()
    return render_template('moradores/form.html', morador=morador, blocos=blocos, apartamentos=apartamentos)

@app.route('/moradores/excluir/<int:id>')
@login_required
def excluir_morador(id):
    conn = conectar()
    cur = conn.cursor()
    try:
        cur.execute('DELETE FROM moradores WHERE id=%s', (id,))
        conn.commit()
    except ForeignKeyViolation:
        conn.rollback()
        conn.close()
        return "Não é possível excluir: existem dados vinculados a esse morador"
    conn.close()
    return redirect('/moradores')

# ── VISITANTES ───────────────────────────────────
@app.route('/visitantes')
@login_required
def listar_visitantes():
    conn = conectar()
    cur = conn.cursor()
    cur.execute('''
        SELECT v.id, v.nome, v.documento, v.morador_id, v.data_hora,
               m.nome, b.nome, a.numero
        FROM visitantes v
        JOIN moradores m ON v.morador_id = m.id
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY v.id DESC
    ''')
    visitantes = cur.fetchall()
    conn.close()
    return render_template('visitantes/listar.html', visitantes=visitantes)

@app.route('/visitantes/novo', methods=['GET', 'POST'])
@login_required
def novo_visitante():
    import requests as req
    conn = conectar()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute('INSERT INTO visitantes (nome, documento, morador_id, data_hora) VALUES (%s,%s,%s,%s)',
                    (request.form['nome'], None,
                     request.form['morador_id'], agora()))
        conn.commit()

        # Busca telefone do morador para notificar
        cur.execute('''
            SELECT m.nome, m.telefone
            FROM moradores m
            WHERE m.id = %s
        ''', (request.form['morador_id'],))
        morador = cur.fetchone()

        if morador and morador[1]:
            fone = ''.join(filter(str.isdigit, morador[1]))
            if not fone.startswith('55'):
                fone = '55' + fone

            evolution_url = os.getenv('EVOLUTION_URL')
            evolution_key = os.getenv('EVOLUTION_KEY')

            try:
                req.post(
                    f'{evolution_url}/message/sendText/portaria',
                    headers={'apikey': evolution_key, 'Content-Type': 'application/json'},
                    json={
                        'number': fone,
                        'text': f'Olá, {morador[0]}! Você tem uma visita: {request.form["nome"]}.'
                    },
                    timeout=5
                )
            except Exception:
                pass  # Não deixa erro do WhatsApp quebrar o registro da visita

        conn.close()
        return redirect('/visitantes')

    cur.execute('''
        SELECT m.id, m.nome, a.numero, b.nome
        FROM moradores m
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    moradores = cur.fetchall()
    conn.close()
    return render_template('visitantes/form.html', moradores=moradores)

@app.route('/visitantes/excluir/<int:id>')
@login_required
def excluir_visitante(id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute('DELETE FROM visitantes WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return redirect('/visitantes')

# ── VEÍCULOS ─────────────────────────────────────
@app.route('/veiculos')
@login_required
def listar_veiculos():
    conn = conectar()
    cur = conn.cursor()
    cur.execute('''
        SELECT v.id, v.placa, v.modelo, v.cor, m.nome, b.nome, a.numero, vg.numero
        FROM veiculos v
        JOIN moradores m ON v.morador_id = m.id
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        LEFT JOIN vagas vg ON vg.veiculo_id = v.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    veiculos = cur.fetchall()
    conn.close()
    return render_template('veiculos/listar.html', veiculos=veiculos)

@app.route('/veiculos/novo', methods=['GET', 'POST'])
@login_required
def novo_veiculo():
    conn = conectar()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute('''
            INSERT INTO veiculos (placa, modelo, cor, morador_id)
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (request.form['placa'], request.form['modelo'],
              request.form['cor'], request.form['morador_id']))
        veiculo_id = cur.fetchone()[0]
        vaga_id = request.form.get('vaga_id')
        if vaga_id:
            cur.execute('UPDATE vagas SET veiculo_id=%s WHERE id=%s', (veiculo_id, vaga_id))
        conn.commit()
        conn.close()
        return redirect('/veiculos')
    cur.execute('''
        SELECT m.id, m.nome, a.numero, b.nome
        FROM moradores m
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    moradores = cur.fetchall()
    cur.execute('SELECT * FROM vagas WHERE veiculo_id IS NULL')
    vagas = cur.fetchall()
    conn.close()
    return render_template('veiculos/form.html', veiculo=None, moradores=moradores, vagas=vagas)

@app.route('/veiculos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_veiculo(id):
    conn = conectar()
    cur = conn.cursor()
    if request.method == 'POST':
        cur.execute('UPDATE veiculos SET placa=%s, modelo=%s, cor=%s, morador_id=%s WHERE id=%s',
                    (request.form['placa'], request.form['modelo'],
                     request.form['cor'], request.form['morador_id'], id))
        cur.execute('UPDATE vagas SET veiculo_id=NULL WHERE veiculo_id=%s', (id,))
        vaga_id = request.form.get('vaga_id')
        if vaga_id:
            cur.execute('UPDATE vagas SET veiculo_id=%s WHERE id=%s', (id, vaga_id))
        conn.commit()
        conn.close()
        return redirect('/veiculos')
    cur.execute('''
        SELECT v.id, v.placa, v.modelo, v.cor, v.morador_id, vg.id
        FROM veiculos v
        LEFT JOIN vagas vg ON vg.veiculo_id = v.id
        WHERE v.id=%s
    ''', (id,))
    veiculo = cur.fetchone()
    cur.execute('''
        SELECT m.id, m.nome, a.numero, b.nome
        FROM moradores m
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    moradores = cur.fetchall()
    cur.execute('SELECT * FROM vagas WHERE veiculo_id IS NULL OR veiculo_id=%s', (id,))
    vagas = cur.fetchall()
    conn.close()
    return render_template('veiculos/form.html', veiculo=veiculo, moradores=moradores, vagas=vagas)

@app.route('/veiculos/excluir/<int:id>')
@login_required
def excluir_veiculo(id):
    conn = conectar()
    cur = conn.cursor()
    try:
        cur.execute('DELETE FROM veiculos WHERE id=%s', (id,))
        conn.commit()
    except ForeignKeyViolation:
        conn.rollback()
        conn.close()
        return "Não é possível excluir: veículo vinculado a uma vaga"
    conn.close()
    return redirect('/veiculos')

# ── VAGAS ────────────────────────────────────────
@app.route('/vagas')
@login_required
def listar_vagas():
    conn = conectar()
    cur = conn.cursor()
    cur.execute('''
        SELECT vg.id, vg.numero, vg.tipo, vg.veiculo_id, v.placa
        FROM vagas vg
        LEFT JOIN veiculos v ON vg.veiculo_id = v.id
        ORDER BY vg.numero
    ''')
    vagas = cur.fetchall()
    conn.close()
    return render_template('veiculos/vagas.html', vagas=vagas)

@app.route('/vagas/nova', methods=['GET', 'POST'])
@login_required
def nova_vaga():
    if request.method == 'POST':
        conn = conectar()
        cur = conn.cursor()
        cur.execute('INSERT INTO vagas (numero, tipo) VALUES (%s, %s)',
                    (request.form['numero'], request.form['tipo']))
        conn.commit()
        conn.close()
        return redirect('/vagas')
    return render_template('veiculos/nova_vaga.html')

@app.route('/vagas/excluir/<int:id>')
@login_required
def excluir_vaga(id):
    conn = conectar()
    cur = conn.cursor()
    try:
        cur.execute('DELETE FROM vagas WHERE id=%s', (id,))
        conn.commit()
    except ForeignKeyViolation:
        conn.rollback()
        conn.close()
        return "Não é possível excluir: vaga está vinculada a um veículo"
    conn.close()
    return redirect('/vagas')

# ── ENCOMENDAS ───────────────────────────────────
@app.route('/encomendas')
@login_required
def listar_encomendas():
    conn = conectar()
    cur = conn.cursor()
    filtro = request.args.get('status')
    query = '''
        SELECT e.id, m.nome, e.descricao, e.remetente, e.data_recebimento,
               e.data_entrega, e.status, b.nome, a.numero,
               CASE WHEN e.foto IS NOT NULL THEN TRUE ELSE FALSE END
        FROM encomendas e
        JOIN moradores m ON e.morador_id = m.id
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        {where}
        ORDER BY e.id DESC
    '''
    if filtro:
        cur.execute(query.format(where='WHERE e.status = %s'), (filtro,))
    else:
        cur.execute(query.format(where=''))
    encomendas = cur.fetchall()
    conn.close()
    return render_template('encomendas/listar.html', encomendas=encomendas, filtro=filtro)

@app.route('/encomendas/nova', methods=['GET', 'POST'])
@login_required
def nova_encomenda():
    conn = conectar()
    cur = conn.cursor()
    erro_foto = None
    if request.method == 'POST':
        foto_dados = None
        foto_mime = None
        arquivo = request.files.get('foto')
        if arquivo and arquivo.filename:
            try:
                foto_dados, foto_mime = validar_foto(arquivo)
            except ValueError as e:
                erro_foto = str(e)
                cur.execute('''
                    SELECT m.id, m.nome, a.numero, b.nome FROM moradores m
                    JOIN apartamentos a ON m.apartamento_id = a.id
                    JOIN blocos b ON a.bloco_id = b.id
                    ORDER BY b.nome, CAST(a.numero AS INTEGER)
                ''')
                moradores = cur.fetchall()
                conn.close()
                return render_template('encomendas/form.html', moradores=moradores, erro_foto=erro_foto)
        cur.execute('''
            INSERT INTO encomendas (morador_id, descricao, remetente, data_recebimento, status, foto, foto_mime)
            VALUES (%s, %s, %s, %s, 'pendente', %s, %s)
        ''', (request.form['morador_id'], request.form['descricao'],
              request.form['remetente'], agora(), foto_dados, foto_mime))
        conn.commit()
        conn.close()
        return redirect('/encomendas')
    cur.execute('''
        SELECT m.id, m.nome, a.numero, b.nome FROM moradores m
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    moradores = cur.fetchall()
    conn.close()
    return render_template('encomendas/form.html', moradores=moradores, erro_foto=None)

@app.route('/encomendas/foto/<int:id>')
@login_required
def foto_encomenda(id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute('SELECT foto, foto_mime FROM encomendas WHERE id = %s', (id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return '', 404
    return send_file(io.BytesIO(bytes(row[0])), mimetype=row[1] or 'image/jpeg', as_attachment=False)

@app.route('/encomendas/apagar-foto/<int:id>')
@login_required
def apagar_foto_encomenda(id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute('UPDATE encomendas SET foto = NULL, foto_mime = NULL WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    return redirect('/encomendas')

@app.route('/encomendas/entregar/<int:id>')
@login_required
def entregar_encomenda(id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute("UPDATE encomendas SET status='entregue', data_entrega=%s WHERE id=%s",
                (agora(), id))
    conn.commit()
    conn.close()
    return redirect('/encomendas')

@app.route('/encomendas/excluir/<int:id>')
@login_required
def excluir_encomenda(id):
    conn = conectar()
    cur = conn.cursor()
    cur.execute('DELETE FROM encomendas WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return redirect('/encomendas')

# ── LOGIN ────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    erro_morador = None
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        if tipo == 'porteiro':
            if request.form['usuario'] == USUARIO and request.form['senha'] == SENHA:
                session['logado'] = True
                return redirect('/')
            erro = 'Usuário ou senha incorretos!'

        elif tipo == 'morador_login':
            apartamento_id = request.form['apartamento_id']
            senha = request.form['senha']
            conn = conectar()
            cur = conn.cursor()
            cur.execute('''
                SELECT c.id, c.nome, c.senha, a.numero, b.nome
                FROM contas_moradores c
                JOIN apartamentos a ON c.apartamento_id = a.id
                JOIN blocos b ON a.bloco_id = b.id
                WHERE c.apartamento_id = %s
            ''', (apartamento_id,))
            contas = cur.fetchall()
            conn.close()
            for conta in contas:
                if check_password_hash(conta[2], senha):
                    session['morador_logado'] = True
                    session['morador_id'] = conta[0]
                    session['morador_nome'] = conta[1]
                    session['morador_ap'] = conta[3]
                    session['morador_bloco'] = conta[4]
                    return redirect('/morador/area')
            erro_morador = 'Apartamento ou senha incorretos!'

        elif tipo == 'morador_registro':
            # O nome é livre — não validamos contra a tabela moradores
            # O que identifica o apartamento é a seleção de bloco/apto
            nome = request.form['nome']
            apartamento_id = request.form['apartamento_id']
            senha = request.form['senha']
            confirmar = request.form['confirmar_senha']
            if senha != confirmar:
                erro_morador = 'As senhas não coincidem!'
            else:
                senha_hash = generate_password_hash(senha)
                conn = conectar()
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO contas_moradores (nome, apartamento_id, senha, criado_em)
                    VALUES (%s, %s, %s, %s)
                ''', (nome, apartamento_id, senha_hash, agora()))
                conn.commit()
                conn.close()
                return redirect('/login?cadastro=ok')

    conn = conectar()
    cur = conn.cursor()
    cur.execute('SELECT * FROM blocos ORDER BY nome')
    blocos = cur.fetchall()
    cur.execute('''
        SELECT a.id, a.numero, b.nome, b.id
        FROM apartamentos a
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    apartamentos = cur.fetchall()
    conn.close()
    cadastro_ok = request.args.get('cadastro') == 'ok'
    return render_template('login.html', erro=erro, erro_morador=erro_morador,
                           blocos=blocos, apartamentos=apartamentos, cadastro_ok=cadastro_ok)

@app.route('/morador/login', methods=['GET', 'POST'])
def login_morador():
    return redirect('/login')

@app.route('/morador/logout')
def logout_morador():
    session.pop('morador_logado', None)
    session.pop('morador_id', None)
    session.pop('morador_nome', None)
    session.pop('morador_ap', None)
    session.pop('morador_bloco', None)
    return redirect('/login')

# ── ÁREA DO MORADOR ──────────────────────────────
@app.route('/morador/area')
def area_morador():
    if not session.get('morador_logado'):
        return redirect('/login')
    return render_template('morador/area.html')

@app.route('/morador/gerar-qr', methods=['GET', 'POST'])
def gerar_qr():
    if not session.get('morador_logado'):
        return redirect('/login')
    qr_base64 = None
    nome_visitante = None
    if request.method == 'POST':
        nome_visitante = request.form['nome_visitante']
        token = secrets.token_urlsafe(32)
        conn = conectar()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO qr_tokens (token, conta_morador_id, nome_visitante, criado_em)
            VALUES (%s, %s, %s, %s)
        ''', (token, session['morador_id'], nome_visitante, agora()))
        conn.commit()
        conn.close()
        url = f"https://sistema-portaria-pwl1.onrender.com/visita/{token}"
        img = qrcode.make(url)
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    return render_template('morador/gerar_qr.html', qr_base64=qr_base64, nome_visitante=nome_visitante)

@app.route('/visita/<token>')
def registrar_visita_qr(token):
    import requests as req
    conn = conectar()
    cur = conn.cursor()
 
    cur.execute('''
        SELECT q.id, q.nome_visitante, q.usado, c.apartamento_id, c.nome, c.morador_id
        FROM qr_tokens q
        JOIN contas_moradores c ON q.conta_morador_id = c.id
        WHERE q.token = %s
    ''', (token,))
    qr = cur.fetchone()
 
    if not qr:
        conn.close()
        return render_template('morador/qr_invalido.html', motivo='QR Code inválido.')
 
    if qr[2] == 1:
        conn.close()
        return render_template('morador/qr_invalido.html', motivo='Este QR Code já foi utilizado.')
 
    # Pega o morador vinculado à conta (morador_id salvo no cadastro)
    # Se não tiver morador_id (contas antigas), cai para qualquer morador do apto
    morador_id = qr[5]
    if morador_id:
        cur.execute('SELECT m.id, m.nome, m.telefone FROM moradores m WHERE m.id = %s', (morador_id,))
    else:
        cur.execute('''
            SELECT m.id, m.nome, m.telefone FROM moradores m
            WHERE m.apartamento_id = %s
            ORDER BY m.id LIMIT 1
        ''', (qr[3],))
    morador = cur.fetchone()
 
    if not morador:
        conn.close()
        return render_template('morador/qr_invalido.html', motivo='Nenhum morador encontrado neste apartamento.')
 
    # Registra a visita
    cur.execute('INSERT INTO visitantes (nome, morador_id, data_hora) VALUES (%s, %s, %s)',
                (qr[1], morador[0], agora()))
    cur.execute('UPDATE qr_tokens SET usado=1 WHERE id=%s', (qr[0],))
    conn.commit()
 
    # Notifica pelo WhatsApp se tiver telefone
    if morador[2]:
        evolution_url = os.getenv('EVOLUTION_URL')
        evolution_key = os.getenv('EVOLUTION_KEY')
        fone = ''.join(filter(str.isdigit, morador[2]))
        if not fone.startswith('55'):
            fone = '55' + fone
        try:
            req.post(
                f'{evolution_url}/message/sendText/portaria',
                headers={'apikey': evolution_key, 'Content-Type': 'application/json'},
                json={
                    'number': fone,
                    'text': f'Olá, {morador[1]}! Você tem uma visita: {qr[1]}.'
                },
                timeout=5
            )
        except Exception:
            pass  # Não deixa erro do WhatsApp quebrar o registro
 
    conn.close()
    return render_template('morador/qr_sucesso.html', nome_visitante=qr[1], nome_morador=qr[4])

@app.route('/contas-moradores')
@login_required
def listar_contas_moradores():
    conn = conectar()
    cur = conn.cursor()
    cur.execute('''
        SELECT c.id, c.nome, c.apartamento_id, a.numero, b.nome, c.criado_em
        FROM contas_moradores c
        JOIN apartamentos a ON c.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER), c.nome
    ''')
    contas = cur.fetchall()
    conn.close()
    return render_template('contas_moradores/listar.html', contas=contas)


@app.route('/contas-moradores/nova', methods=['GET', 'POST'])
@login_required
def nova_conta_morador():
    conn = conectar()
    cur = conn.cursor()
    erro = None
 
    if request.method == 'POST':
        morador_id = request.form['morador_id']
        senha = request.form['senha']
        confirmar = request.form['confirmar_senha']
 
        if senha != confirmar:
            erro = 'As senhas não coincidem!'
        else:
            # Pega nome e apartamento diretamente do morador selecionado
            cur.execute('''
                SELECT m.nome, m.apartamento_id
                FROM moradores m
                WHERE m.id = %s
            ''', (morador_id,))
            morador = cur.fetchone()
 
            if not morador:
                erro = 'Morador não encontrado.'
            else:
                senha_hash = generate_password_hash(senha)
                cur.execute('''
                    INSERT INTO contas_moradores (nome, apartamento_id, senha, criado_em, morador_id)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (morador[0], morador[1], senha_hash, agora(), morador_id))
                conn.commit()
                conn.close()
                return redirect('/contas-moradores')
 
    cur.execute('''
        SELECT m.id, m.nome, a.numero, b.nome
        FROM moradores m
        JOIN apartamentos a ON m.apartamento_id = a.id
        JOIN blocos b ON a.bloco_id = b.id
        ORDER BY b.nome, CAST(a.numero AS INTEGER)
    ''')
    moradores = cur.fetchall()
    conn.close()
    return render_template('contas_moradores/form.html', moradores=moradores, erro=erro)


@app.route('/contas-moradores/excluir/<int:id>')
@login_required
def excluir_conta_morador(id):
    conn = conectar()
    cur = conn.cursor()
    # Apaga os QR tokens vinculados primeiro
    cur.execute('DELETE FROM qr_tokens WHERE conta_morador_id=%s', (id,))
    cur.execute('DELETE FROM contas_moradores WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return redirect('/contas-moradores')

import requests

@app.route('/qrcode-portaria')
@login_required
def qrcode_portaria():
    import requests as req
    evolution_url = os.getenv('EVOLUTION_URL')
    evolution_key = os.getenv('EVOLUTION_KEY')
    try:
        res = req.get(
            f'{evolution_url}/instance/connect/portaria',
            headers={'apikey': evolution_key},
            timeout=10
        )
        if res.status_code != 200 or not res.text.strip():
            return f'Erro na API. Status: {res.status_code}', 500
        data = res.json()
        base64 = data.get('base64', '')
        if not base64:
            # WhatsApp já conectado!
            return '''<!DOCTYPE html><html><head><meta charset="UTF-8">
            <title>WhatsApp</title></head><body style="font-family:Arial;text-align:center;padding:40px">
            <h2 style="color:#1f4d35">WhatsApp já conectado!</h2>
            <p>O número da portaria está ativo.</p>
            <a href="/" style="background:#1f4d35;color:white;padding:10px 24px;border-radius:8px;text-decoration:none">Voltar</a>
            </body></html>'''
        return f'''<!DOCTYPE html><html><head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
        <title>QR Code WhatsApp</title>
        <style>
            body {{ font-family: Arial; display: flex; align-items: center; justify-content: center;
                   min-height: 100vh; margin: 0; background: #f0f0f0; }}
            .card {{ background: white; border-radius: 16px; padding: 32px; text-align: center;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.1); max-width: 380px; width: 100%; }}
            h2 {{ color: #1f4d35; }} p {{ color: #666; font-size: 0.9rem; }}
            img {{ width: 280px; margin: 16px 0; }}
            a {{ display: inline-block; margin-top: 16px; background: #1f4d35; color: white;
                padding: 10px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; }}
        </style></head><body>
        <div class="card">
            <h2>WhatsApp Portaria</h2>
            <p>Abra o WhatsApp → três pontinhos → Aparelhos conectados → Conectar aparelho</p>
            <img src="{base64}">
            <br>
            <a href="/qrcode-portaria">Atualizar QR Code</a>
        </div></body></html>'''
    except Exception as e:
        return f'Erro: {e}', 500

@app.route('/encomendas/notificar/<int:id>')
@login_required
def notificar_encomenda(id):
    import requests as req
    conn = conectar()
    cur = conn.cursor()
    cur.execute('''
        SELECT e.id, e.descricao, e.remetente, e.foto, e.foto_mime,
               m.nome, m.telefone
        FROM encomendas e
        JOIN moradores m ON e.morador_id = m.id
        WHERE e.id = %s
    ''', (id,))
    e = cur.fetchone()

    if not e:
        conn.close()
        return redirect('/encomendas')

    telefone = e[6]
    if not telefone:
        conn.close()
        return redirect('/encomendas')

    # Limpa o telefone — deixa só números
    fone = ''.join(filter(str.isdigit, telefone))
    # Adiciona 55 (Brasil) se não tiver
    if not fone.startswith('55'):
        fone = '55' + fone

    evolution_url = os.getenv('EVOLUTION_URL')
    evolution_key = os.getenv('EVOLUTION_KEY')
    headers = {'apikey': evolution_key, 'Content-Type': 'application/json'}

    remetente = e[2] or 'não informado'
    mensagem = f"Olá, {e[5]}! Chegou uma encomenda para você. Remetente: {remetente}."

    # Envia a foto se tiver
    if e[3]:
        import base64 as b64
        foto_b64 = b64.b64encode(bytes(e[3])).decode()
        mime = e[4] or 'image/jpeg'
        req.post(f'{evolution_url}/message/sendMedia/portaria', headers=headers, json={
            'number': fone,
            'mediatype': 'image',
            'media': foto_b64,
            'caption': mensagem
        })
        # Apaga a foto do banco após enviar
        cur.execute('UPDATE encomendas SET foto = NULL, foto_mime = NULL WHERE id = %s', (id,))
    else:
        # Sem foto — envia só texto
        req.post(f'{evolution_url}/message/sendText/portaria', headers=headers, json={
            'number': fone,
            'text': mensagem
        })

    conn.commit()
    conn.close()
    return redirect('/encomendas')
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
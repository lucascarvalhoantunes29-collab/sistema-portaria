import psycopg
import os

def conectar():
    return psycopg.connect(os.environ.get('DATABASE_URL'))

def criar_tabelas():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS apartamentos (
            id SERIAL PRIMARY KEY,
            numero TEXT NOT NULL,
            bloco_id INTEGER REFERENCES blocos(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS moradores (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            apartamento_id INTEGER REFERENCES apartamentos(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visitantes (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            documento TEXT,
            morador_id INTEGER REFERENCES moradores(id),
            data_hora TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS veiculos (
            id SERIAL PRIMARY KEY,
            placa TEXT NOT NULL,
            modelo TEXT,
            cor TEXT,
            morador_id INTEGER REFERENCES moradores(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vagas (
            id SERIAL PRIMARY KEY,
            numero TEXT NOT NULL,
            tipo TEXT,
            veiculo_id INTEGER REFERENCES veiculos(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS encomendas (
            id SERIAL PRIMARY KEY,
            morador_id INTEGER REFERENCES moradores(id),
            descricao TEXT NOT NULL,
            remetente TEXT,
            data_recebimento TEXT NOT NULL,
            data_entrega TEXT,
            status TEXT NOT NULL DEFAULT 'pendente'
        )
    ''')

    # Adiciona colunas de foto se ainda não existirem (seguro rodar várias vezes)
    cursor.execute('''
        ALTER TABLE encomendas
        ADD COLUMN IF NOT EXISTS foto BYTEA
    ''')
    cursor.execute('''
        ALTER TABLE encomendas
        ADD COLUMN IF NOT EXISTS foto_mime TEXT
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contas_moradores (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            apartamento_id INTEGER REFERENCES apartamentos(id),
            senha TEXT NOT NULL,
            criado_em TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qr_tokens (
            id SERIAL PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            conta_morador_id INTEGER REFERENCES contas_moradores(id),
            nome_visitante TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            usado INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    conn.close()
    print('Tabelas criadas com sucesso!')
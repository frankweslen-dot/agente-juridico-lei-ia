import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Agente Jurídico IA", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS (MEMÓRIA) ---
def connect_to_sheets():
    try:
        # Pega as credenciais do cofre do Streamlit
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["connections"]["gsheets"]["creds"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        # Abre a planilha
        sheet = client.open("base_juridica_ia")
        return sheet
    except Exception as e:
        st.error(f"Erro ao conectar na planilha: {e}")
        return None

# --- FUNÇÕES DE SEGURANÇA E USUÁRIOS ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def carregar_usuarios(sheet):
    worksheet = sheet.worksheet("usuarios")
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

def registrar_usuario(sheet, nome, usuario, senha):
    worksheet = sheet.worksheet("usuarios")
    senha_hash = hash_password(senha)
    # Adiciona nova linha: username, password, name, cities, permissions, status
    worksheet.append_row([usuario, senha_hash, nome, "NENHUMA", "LER", "Pendente"])

def atualizar_usuario(sheet, usuario_alvo, nova_cidade, novo_status, nova_permissao):
    worksheet = sheet.worksheet("usuarios")
    cell = worksheet.find(usuario_alvo)
    # Atualiza colunas: D (Cidade), E (Permissao), F (Status)
    worksheet.update_cell(cell.row, 4, nova_cidade)
    worksheet.update_cell(cell.row, 5, nova_permissao)
    worksheet.update_cell(cell.row, 6, novo_status)

# --- CONFIGURAÇÃO GEMINI ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("Configure a GOOGLE_API_KEY nos Secrets.")

# --- INTERFACE PRINCIPAL ---

# Conecta ao banco
sheet = connect_to_sheets()

if "logado" not in st.session_state:
    st.session_state["logado"] = False
    st.session_state["usuario_atual"] = {}

# TELA DE LOGIN / CADASTRO
if not st.session_state["logado"]:
    st.title("⚖️ Sistema de Inteligência Jurídica")
    tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])

    with tab1: # Login
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            if sheet:
                try:
                    df_users = carregar_usuarios(sheet)
                    # Verifica se usuário existe
                    user_match = df_users[df_users['username'] == usuario]
                    
                    if not user_match.empty:
                        # Verifica senha e status
                        stored_pass = str(user_match.iloc[0]['password'])
                        # Tenta pegar o status, se não existir assume Aprovado (para compatibilidade)
                        status = str(user_match.iloc[0]['status']) if 'status' in user_match.columns else 'Aprovado'
                        
                        if stored_pass == hash_password(senha):
                            if status == "Aprovado" or usuario == "admin": # Admin sempre entra
                                st.session_state["logado"] = True
                                st.session_state["usuario_atual"] = user_match.iloc[0].to_dict()
                                st.rerun()
                            else:
                                st.warning("🔒 Seu cadastro ainda está pendente de aprovação.")
                        else:
                            st.error("Senha incorreta.")
                    else:
                        st.error("Usuário não encontrado.")
                except Exception as e:
                    st.error(f"Erro ao ler usuários: {e}")

    with tab2: # Cadastro
        novo_nome = st.text_input("Nome Completo")
        novo_user = st.text_input("Escolha um Usuário")
        nova_senha = st.text_input("Escolha uma Senha", type="password")
        if st.button("Solicitar Acesso"):
            if sheet:
                try:
                    df_users = carregar_usuarios(sheet)
                    if novo_user in df_users['username'].values:
                        st.error("Este usuário já existe.")
                    else:
                        registrar_usuario(sheet, novo_nome, novo_user, nova_senha)
                        st.success("Cadastro enviado! Aguarde aprovação do administrador.")
                except Exception as e:
                     st.error(f"Erro no cadastro: {e}")

# TELA DO SISTEMA (APÓS LOGIN)
else:
    user = st.session_state["usuario_atual"]
    
    # BARRA LATERAL
    with st.sidebar:
        st.write(f"Olá, **{user['name']}**")
        st.write(f"Permissão: `{user.get('permissions', 'LER')}`")
        if st.button("Sair"):
            st.session_state["logado"] = False
            st.rerun()
    
    # ÁREA DO ADMINISTRADOR
    permissions = str(user.get('permissions', ''))
    if "DELETE" in permissions or user['username'] == 'admin':
        with st.expander("👮 Painel de Gestão de Usuários (Admin)", expanded=True):
            st.write("Gerencie quem pode acessar o sistema.")
            if sheet:
                df_users = carregar_usuarios(sheet)
                
                # Edição rápida
                lista_usuarios = df_users['username'].tolist()
                edit_user = st.selectbox("Selecione o Usuário para Editar", lista_usuarios)
                
                if edit_user:
                    user_data = df_users[df_users['username'] == edit_user].iloc[0]
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        current_status = user_data.get('status', 'Pendente')
                        status_opts = ["Pendente", "Aprovado", "Bloqueado"]
                        index_status = status_opts.index(current_status) if current_status in status_opts else 0
                        new_status = st.selectbox("Status", status_opts, index=index_status)
                    with col2:
                        new_city = st.text_input("Cidades (separar por vírgula)", value=user_data.get('cities', ''))
                    with col3:
                        perm_opts = ["LER", "LER,UPLOAD", "LER,UPLOAD,DELETE"]
                        current_perm = user_data.get('permissions', 'LER')
                        index_perm = perm_opts.index(current_perm) if current_perm in perm_opts else 0
                        new_perm = st.selectbox("Nível", perm_opts, index=index_perm)
                    
                    if st.button("💾 Atualizar Usuário"):
                        atualizar_usuario(sheet, edit_user, new_city, new_status, new_perm)
                        st.success(f"Dados de {edit_user} atualizados!")
                        st.rerun()

    # ÁREA COMUM (CHAT E LEIS)
    st.divider()
    cidades_permitidas = user.get('cities', 'Nenhuma')
    st.subheader(f"Jurisprudência: {cidades_permitidas}")
    
    # Upload (Apenas se tiver permissão)
    if "UPLOAD" in permissions:
        uploaded_file = st.file_uploader("Enviar nova Lei (PDF)", type="pdf")
        if uploaded_file:
            st.success("Arquivo recebido temporariamente (Conectaremos o Drive na próxima etapa!)")

    # Chat com IA
    prompt = st.chat_input("Pergunte sobre as leis municipais...")
    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            st.write("🤖 Analisando sua pergunta...")
            # Lógica do Gemini conectada aqui
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(f"O usuário perguntou: {prompt}. Responda como um assistente jurídico.")
                st.write(response.text)
            except Exception as e:
                st.error(f"Erro na IA: {e}")

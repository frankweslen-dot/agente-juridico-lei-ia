import streamlit as st
import google.generativeai as genai
import pandas as pd
import hashlib
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import json
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Leis Municipais IA", layout="wide")

# --- ID DA PASTA DO DRIVE ---
PASTA_DRIVE_ID = "1lJrCodOa3YPRU_6ak5rUpGGP20bOjeMl"

# --- CONEXÃO COM GOOGLE (DRIVE + SHEETS) ---
def connect_google():
    try:
        # Carrega credenciais dos Secrets
        creds_dict = json.loads(st.secrets["connections"]["gsheets"]["creds"])
        
        # Define escopos para Drive e Planilhas
        scopes = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets"
        ]
        
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=scopes
        )
        
        # Conecta nos serviços
        drive_service = build('drive', 'v3', credentials=creds)
        client_sheets = gspread.authorize(creds)
        sheet = client_sheets.open("base_juridica_ia")
        
        return drive_service, sheet
    except Exception as e:
        st.error(f"Erro na conexão Google: {e}")
        return None, None

# --- FUNÇÕES DE ARQUIVO E DRIVE ---
def salvar_arquivo_drive(drive_service, arquivo_upload, nome_arquivo, pasta_id):
    try:
        file_metadata = {
            'name': nome_arquivo,
            'parents': [pasta_id]
        }
        media = MediaIoBaseUpload(arquivo_upload, mimetype='application/pdf')
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"Erro no Upload para o Drive: {e}")
        return None

def calcular_hash(arquivo):
    # Calcula um código único para o arquivo (evita duplicatas e garante integridade)
    pos_original = arquivo.tell()
    arquivo.seek(0)
    file_hash = hashlib.md5(arquivo.read()).hexdigest()
    arquivo.seek(pos_original)
    return file_hash

def registrar_lei_na_planilha(sheet, cidade, nome_arq, link, usuario_logado, arquivo_upload):
    try:
        worksheet = sheet.worksheet("leis")
        data_hoje = datetime.now().strftime("%d/%m/%Y")
        
        # 1. Calcula o Hash
        hash_arquivo = calcular_hash(arquivo_upload)
        
        # 2. Cria o Filename clicável (Fórmula do Sheets)
        filename_clicavel = f'=HYPERLINK("{link}"; "{nome_arq}")'
        
        # 3. Define o texto completo (VAZIO por enquanto, para economizar espaço)
        texto_completo = "" 
        
        # Colunas exatas da sua planilha: 
        # filename; upload_date; uploader; city; full_text; file_hash
        worksheet.append_row([
            filename_clicavel, 
            data_hoje, 
            usuario_logado, 
            cidade, 
            texto_completo, 
            hash_arquivo
        ], value_input_option='USER_ENTERED') 
        
        return True
    except Exception as e:
        st.error(f"Erro ao salvar na planilha: {e}")
        return False

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
    worksheet.append_row([usuario, senha_hash, nome, "NENHUMA", "LER", "Pendente"])

def atualizar_usuario(sheet, usuario_alvo, nova_cidade, novo_status, nova_permissao):
    worksheet = sheet.worksheet("usuarios")
    cell = worksheet.find(usuario_alvo)
    worksheet.update_cell(cell.row, 4, nova_cidade)
    worksheet.update_cell(cell.row, 5, nova_permissao)
    worksheet.update_cell(cell.row, 6, novo_status)

def alterar_senha_usuario(sheet, usuario_alvo, nova_senha):
    worksheet = sheet.worksheet("usuarios")
    cell = worksheet.find(usuario_alvo)
    nova_senha_hash = hash_password(nova_senha)
    worksheet.update_cell(cell.row, 2, nova_senha_hash)

# --- CONFIGURAÇÃO GEMINI ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("Configure a GOOGLE_API_KEY nos Secrets.")

# --- INTERFACE PRINCIPAL ---

drive_service, sheet = connect_google()

if "logado" not in st.session_state:
    st.session_state["logado"] = False
    st.session_state["usuario_atual"] = {}
if "cidade_selecionada" not in st.session_state:
    st.session_state["cidade_selecionada"] = None

# TELA DE LOGIN / CADASTRO
if not st.session_state["logado"]:
    
    # --- CABEÇALHO DA TELA DE LOGIN ---
    st.markdown("""
        <h1 style='margin-bottom: -15px;'>🏛️ Leis Municipais IA</h1>
        <small style='color: grey; font-size: 12px;'>© Lopes & Souto Advogados Associados</small>
        <hr style='margin-top: 5px; margin-bottom: 20px;'>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])

    with tab1:
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            if sheet:
                try:
                    df_users = carregar_usuarios(sheet)
                    user_match = df_users[df_users['username'] == usuario]
                    if not user_match.empty:
                        stored_pass = str(user_match.iloc[0]['password'])
                        status = str(user_match.iloc[0]['status']) if 'status' in user_match.columns else 'Aprovado'
                        if stored_pass == hash_password(senha):
                            if status == "Aprovado" or usuario == "admin":
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

    with tab2:
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
                        st.success("Cadastro enviado! Aguarde aprovação.")
                except Exception as e:
                     st.error(f"Erro no cadastro: {e}")

# ÁREA INTERNA (LOGADO)
else:
    user = st.session_state["usuario_atual"]
    
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.markdown("""
            <h2 style='margin-bottom: -10px;'>🏛️ Leis Municipais IA</h2>
            <small style='color: grey; font-size: 11px;'>© Lopes & Souto Advogados Associados</small>
            <hr style='margin-top: 5px; margin-bottom: 15px;'>
        """, unsafe_allow_html=True)

        st.header(f"Olá, {user['name']}")
        st.caption(f"Perfil: {user.get('permissions', 'LER')}")
        
        st.divider()
        st.subheader("📍 Seus Acessos")
        lista_cidades_raw = str(user.get('cities', '')).split(',')
        lista_cidades = [c.strip() for c in lista_cidades_raw if c.strip() != ""]
        
        if "TODAS" in user.get('cities', ''):
             st.info("🌍 Acesso Global")
             if len(lista_cidades) <= 1:
                 lista_cidades = ["São Paulo", "Rio de Janeiro", "Belo Horizonte"]
        else:
            for cidade in lista_cidades:
                st.write(f"• {cidade}")

        st.divider()
        if st.button("Sair"):
            st.session_state["logado"] = False
            st.session_state["cidade_selecionada"] = None
            st.rerun()

        with st.expander("🔑 Alterar Senha"):
            senha_atual = st.text_input("Senha Atual", type="password")
            nova_senha_1 = st.text_input("Nova Senha", type="password")
            nova_senha_2 = st.text_input("Confirmar", type="password")
            if st.button("Salvar"):
                if hash_password(senha_atual) == str(user['password']):
                    if nova_senha_1 == nova_senha_2 and nova_senha_1 != "":
                        alterar_senha_usuario(sheet, user['username'], nova_senha_1)
                        st.success("Senha alterada! Relogue.")
                        st.session_state["logado"] = False
                        st.rerun()
                    else:
                        st.error("Senhas não conferem.")
                else:
                    st.error("Senha atual errada.")
    
    # FLUXO DE SELEÇÃO DE CIDADE
    if not st.session_state["cidade_selecionada"]:
        st.title("Bem-vindo ao Sistema")
        st.info("👈 Confira seus acessos na barra lateral.")
        
        st.subheader("Com qual município deseja trabalhar agora?")
        escolha = st.selectbox("Selecione na lista:", lista_cidades)
        
        if st.button(f"Acessar Painel de {escolha}"):
            st.session_state["cidade_selecionada"] = escolha
            st.rerun()

    # PAINEL DA CIDADE
    else:
        cidade_atual = st.session_state["cidade_selecionada"]
        
        col_voltar, col_titulo = st.columns([1, 5])
        with col_voltar:
            if st.button("⬅ Trocar"):
                st.session_state["cidade_selecionada"] = None
                st.rerun()
        with col_titulo:
            st.title(f"🏛️ Painel: {cidade_atual}")
        
        # ESTATÍSTICAS REAIS (Contando da Planilha)
        total_organica = 0
        total_compl = 0
        total_ordinaria = 0
        total_decreto = 0
        
        # Tenta ler a aba 'leis' para contar
        try:
            if sheet:
                ws_leis = sheet.worksheet("leis")
                todas_leis = ws_leis.get_all_records()
                df_leis = pd.DataFrame(todas_leis)
                
                # Filtra pela cidade atual e conta baseado no nome do arquivo
                if not df_leis.empty and 'city' in df_leis.columns:
                    df_cidade = df_leis[df_leis['city'] == cidade_atual]
                    
                    # Como não temos coluna 'tipo', procuramos o texto dentro do 'filename'
                    # pois salvamos como "Cidade_Tipo_Nome"
                    total_organica = df_cidade['filename'].astype(str).str.contains("Lei Orgânica").sum()
                    total_compl = df_cidade['filename'].astype(str).str.contains("Lei Complementar").sum()
                    total_ordinaria = df_cidade['filename'].astype(str).str.contains("Lei Ordinária").sum()
                    total_decreto = df_cidade['filename'].astype(str).str.contains("Decreto").sum()
        except Exception as e:
            # st.error(f"Erro estatistica: {e}") # Comentado para não sujar a tela se estiver vazia
            pass

        st.markdown("### 📊 Acervo Digital")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Lei Orgânica", int(total_organica))
        col2.metric("Leis Complementares", int(total_compl))
        col3.metric("Leis Ordinárias", int(total_ordinaria))
        col4.metric("Decretos", int(total_decreto))
        
        with st.expander("📂 Visualizar Índice Completo"):
            if 'df_cidade' in locals() and not df_cidade.empty:
                # Mostra apenas colunas relevantes para o usuário
                st.dataframe(df_cidade[['upload_date', 'filename', 'uploader']])
            else:
                st.info("Nenhum documento encontrado para esta cidade.")

        st.divider()

        # ÁREA DE TRABALHO
        permissions = str(user.get('permissions', ''))
        
        tab_consulta, tab_gestao = st.tabs(["💬 Consultar IA", "📤 Gestão de Arquivos"])
        
        with tab_consulta:
            st.subheader(f"Assistente Jurídico de {cidade_atual}")
            prompt = st.chat_input(f"Pergunte sobre as leis de {cidade_atual}...")
            if prompt:
                with st.chat_message("user"):
                    st.write(prompt)
                with st.chat_message("assistant"):
                    st.write("🤖 Analisando...")
                    try:
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        # Prompt básico (sem injeção de texto por enquanto)
                        response = model.generate_content(f"Você é um assistente jurídico especialista em {cidade_atual}. Responda: {prompt}")
                        st.write(response.text)
                    except Exception as e:
                        st.error(f"Erro na IA: {e}")

        with tab_gestao:
            if "UPLOAD" in permissions:
                st.write("Envie novos arquivos para a base desta cidade.")
                uploaded_file = st.file_uploader("Selecione o PDF", type="pdf")
                tipo_lei = st.selectbox("Tipo de Norma", ["Lei Ordinária", "Lei Complementar", "Decreto", "Lei Orgânica"])
                
                if uploaded_file and st.button("📤 Salvar no Banco de Dados"):
                    with st.spinner("Enviando para o Google Drive..."):
                        # 1. Salvar no Drive
                        nome_final = f"{cidade_atual}_{tipo_lei}_{uploaded_file.name}"
                        link_drive = salvar_arquivo_drive(drive_service, uploaded_file, nome_final, PASTA_DRIVE_ID)
                        
                        if link_drive:
                            # 2. Registrar na Planilha
                            sucesso = registrar_lei_na_planilha(
                                sheet, 
                                cidade_atual, 
                                nome_final, 
                                link_drive, 
                                user['username'], 
                                uploaded_file
                            )
                            if sucesso:
                                st.success(f"Sucesso! Arquivo salvo e registrado.")
                                st.balloons()
                                st.cache_data.clear()
                            else:
                                st.error("Salvo no Drive, mas erro ao registrar na planilha.")
                        else:
                            st.error("Erro ao salvar no Google Drive.")
            else:
                st.warning("Você não tem permissão para enviar arquivos.")

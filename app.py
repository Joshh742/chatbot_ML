from flask import Flask, request, jsonify
import requests
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

app = Flask(__name__)

# --- KONFIGURASI ENV ---
load_dotenv()
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not FONNTE_TOKEN or not GEMINI_API_KEY:
    print("FATAL ERROR: Pastikan FONNTE_TOKEN dan GEMINI_API_KEY ada di file .env Anda!")

# --- KONFIGURASI GEMINI ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    print("Koneksi ke Gemini API berhasil.")
except Exception as e:
    print(f"ERROR FATAL SAAT STARTUP: Gagal konfigurasi Gemini: {e}")

# --- DATABASE & CONSTANT ---
DATABASE_OBAT = []
USERS_DB = {} 
MAX_HISTORY_LIMIT = 20  

def load_database_obat():
    global DATABASE_OBAT
    try:
        if not os.path.exists('database_obat.json'):
             with open('database_obat.json', 'w') as f: json.dump([], f)
        
        with open('database_obat.json', 'r', encoding='utf-8') as f:
            DATABASE_OBAT = json.load(f)
        print(f"Berhasil memuat {len(DATABASE_OBAT)} data obat.")
    except Exception as e:
        print(f"ERROR: Gagal memuat database_obat.json: {e}")

def load_users():
    """Memuat data user DAN riwayat chat dari file JSON"""
    global USERS_DB
    try:
        if not os.path.exists('users.json'):
            with open('users.json', 'w') as f:
                json.dump({}, f)
        
        with open('users.json', 'r', encoding='utf-8') as f:
            USERS_DB = json.load(f)
        print(f"Berhasil memuat {len(USERS_DB)} data pengguna.")
    except Exception as e:
        print(f"ERROR: Gagal memuat users.json: {e}")

def save_users():
    """Menyimpan data user termasuk history chat ke file JSON"""
    try:
        with open('users.json', 'w', encoding='utf-8') as f:
            json.dump(USERS_DB, f, indent=2)
    except Exception as e:
        print(f"ERROR: Gagal menyimpan users.json: {e}")

def kirim_balasan_fonnte(nomor_tujuan, teks_balasan):
    url_api_fonnte = "https://api.fonnte.com/send"
    headers = {"Authorization": FONNTE_TOKEN}
    payload = {"target": nomor_tujuan, "message": teks_balasan}
    
    try:
        response = requests.post(url_api_fonnte, headers=headers, data=payload)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Gagal mengirim balasan ke Fonnte: {e}")

def panggil_gemini_dengan_memori(pesan_baru, nama_user, history_user):
    """
    Mengirim pesan ke Gemini dengan menyertakan riwayat percakapan sebelumnya
    dan instruksi sistem yang dinamis sesuai nama user.
    """
    instruksi_khusus = (
        f"Anda adalah asisten kesehatan AI yang ramah. "
        f"Nama pengguna yang sedang Anda ajak bicara adalah: {nama_user}. "
        f"Sapa dia dengan namanya sesekali agar terasa personal. "
        "Peran Anda adalah menjawab pertanyaan pengguna tentang kesehatan. "
        "Jika ditanya obat, sebutkan obat bebas (OTC), dan jika tidak ada obat (OTC) sebutkan saja obat selain (OTC) dan pola hidup sehat. "
        "Akhiri jawaban dengan disclaimer bahwa Anda AI dan bukan dokter. "
        "Langung simpulkan obat nya apa baik OTC atau bukan OTC, serta pola hidup sehat yang dianjurkan. "
        "Jangan memberikan saran medis yang rumit atau diagnosis, buatkan jawaban yang mudah dimengerti, dan singkat. "
        "Jangan gunakan tanda bintang (*) untuk formatting, gunakan teks biasa."
        "Jika menanyakan pola hidup hanya jelaskan pola hidup, jika tanya penyakit hanya jelaskan penyakit, dan jika tanya obat hanya jelaskan dan berikan obatnya."
    )

    try:
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction=instruksi_khusus
        )

        # 1. Mulai sesi chat dengan history yang ada
        chat_session = model.start_chat(history=history_user)
        
        # 2. Kirim pesan baru
        response = chat_session.send_message(pesan_baru)
        
        # Hapus tanda bintang 
        teks_bersih = response.text.replace('*', '') 
        
        # 3. Ambil history terbaru dari object chat_session
        updated_history = []
        for content in chat_session.history:
            role = content.role
            text_part = content.parts[0].text if content.parts else ""
            updated_history.append({"role": role, "parts": [text_part]})

        # Jaga agar history tidak terlalu panjang
        if len(updated_history) > MAX_HISTORY_LIMIT:
            updated_history = updated_history[-MAX_HISTORY_LIMIT:]

        return teks_bersih, updated_history

    except Exception as e:
        print(f"ERROR Gemini Chat: {e}")
        return "Maaf, saya sedikit pusing. Bisakah diulangi?", history_user

# --- LOGIKA UTAMA ---
def proses_pesan(pesan_masuk, nomor_pengirim):
    teks = pesan_masuk.strip() 
    
    # 1. CEK IDENTITAS PENGGUNA
    if nomor_pengirim not in USERS_DB:
        USERS_DB[nomor_pengirim] = {
            'nama': None, 
            'status': 'menunggu_nama', 
            'history': [] 
        }
        save_users()
        return "Halo! Selamat datang di PilBot, Saya adalah asisten kesehatan AI\nSebelum kita mulai, bolehkah saya tahu siapa nama panggilan Anda?"

    user_data = USERS_DB[nomor_pengirim]

    if 'history' not in user_data:
        user_data['history'] = []

    # 2. PROSES PENYIMPANAN NAMA 
    if user_data.get('status') == 'menunggu_nama':
        nama_baru = teks 
        USERS_DB[nomor_pengirim]['nama'] = nama_baru
        USERS_DB[nomor_pengirim]['status'] = 'registered' 
        save_users()
        return (f"Salam kenal, {nama_baru}! Data Anda sudah saya simpan.\n\n"
                "Sekarang Anda bisa bertanya tentang penyakit atau obat, dan saya akan mengingat percakapan kita.")

    nama_user = user_data['nama']
    teks_lower = teks.lower()

    # 3. COMMAND KHUSUS
    if teks_lower in ['reset', 'ganti nama penyakit', 'ganti penyakit', 'ganti topik', 'topik baru']:
        USERS_DB[nomor_pengirim]['history'] = []
        save_users()
        return "Oke, ingatan saya tentang penyakit sebelumnya sudah dihapus. Silakan tanyakan tentang penyakit baru (misalnya demam), saya siap mengingatnya!"

    if teks_lower == 'ganti nama':
        USERS_DB[nomor_pengirim]['status'] = 'menunggu_nama'
        save_users()
        return "Oke, silakan ketik nama baru Anda:"

    # 4. LOGIKA CHATBOT DENGAN MEMORI
    print(f"User {nama_user} bertanya: {teks} (History len: {len(user_data['history'])})")
    
    balasan, history_baru = panggil_gemini_dengan_memori(teks, nama_user, user_data['history'])
    
    USERS_DB[nomor_pengirim]['history'] = history_baru
    save_users() 
    
    return balasan

# WEBHOOK ENDPOINT 
@app.route('/webhook-fonnte', methods=['POST'])
def webhook_fonnte():
    try:
        data = request.json
        pesan_masuk = data.get('message')
        nomor_pengirim = data.get('sender')
        is_group = data.get('isGroup', False)
        
        if pesan_masuk and nomor_pengirim and not is_group:
            teks_balasan = proses_pesan(pesan_masuk, nomor_pengirim)
            kirim_balasan_fonnte(nomor_pengirim, teks_balasan)
            
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"ERROR webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Jalankan Server 
if __name__ == '__main__':
    load_database_obat()
    load_users()
    print("Server chatbot berjalan dengan fitur Memori Percakapan & Instruksi Baru...")
    app.run(debug=True, port=5000)
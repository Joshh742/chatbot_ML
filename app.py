from flask import Flask, request, jsonify
import requests
import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not FONNTE_TOKEN or not GEMINI_API_KEY:
    print("FATAL ERROR: Pastikan FONNTE_TOKEN dan GEMINI_API_KEY ada di file .env Anda!")

model = None 
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("Koneksi ke Gemini API berhasil.")
except Exception as e:
    print(f"ERROR FATAL SAAT STARTUP: Gagal konfigurasi Gemini: {e}")

# --- DATABASE ---
DATABASE_OBAT = []
USERS_DB = {} # Dictionary untuk menyimpan data user {nomor: {'nama': 'Budi', 'status': 'active'}}

def load_database_obat():
    global DATABASE_OBAT
    try:
        # Buat file dummy jika tidak ada agar tidak error
        if not os.path.exists('database_obat.json'):
             with open('database_obat.json', 'w') as f: json.dump([], f)
        
        with open('database_obat.json', 'r', encoding='utf-8') as f:
            DATABASE_OBAT = json.load(f)
        print(f"Berhasil memuat {len(DATABASE_OBAT)} data obat.")
    except Exception as e:
        print(f"ERROR: Gagal memuat database_obat.json: {e}")

def load_users():
    """Memuat data user dari file JSON agar ingatan tidak hilang saat restart"""
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
    """Menyimpan data user ke file JSON"""
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
        # response.raise_for_status() # Opsional: uncomment jika ingin strict
        print(f"Berhasil mengirim balasan ke {nomor_tujuan}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Gagal mengirim balasan ke Fonnte: {e}")

def panggil_gemini(pertanyaan, nama_user):
    """
    Mengirim pertanyaan ke Gemini API dengan konteks NAMA PENGGUNA.
    """
    if model is None:
        return "Maaf, AI sedang mengalami gangguan."

    instruksi_tugas = (
        f"Anda adalah asisten kesehatan AI yang ramah. "
        f"Nama pengguna yang sedang Anda ajak bicara adalah: {nama_user}. "
        f"Sapa dia dengan namanya sesekali agar terasa personal. "
        "Peran Anda adalah menjawab pertanyaan pengguna tentang kesehatan. "
        "Jika ditanya obat, sebutkan obat bebas (OTC) dan pola hidup sehat. "
        "Akhiri jawaban dengan disclaimer bahwa Anda AI dan bukan dokter. "
        "Jangan gunakan tanda bintang (*) untuk formatting, gunakan teks biasa."
    )

    try:
        response = model.generate_content(f"{instruksi_tugas}\n\nPertanyaan {nama_user}: {pertanyaan}")
        teks_bersih = response.text.replace('*', '')
        return teks_bersih
    except Exception as e:
        print(f"ERROR Gemini: {e}")
        return "Maaf, AI sedang sibuk. Coba lagi nanti."

# --- LOGIKA UTAMA ---
def proses_pesan(pesan_masuk, nomor_pengirim):
    """
    Sekarang menerima nomor_pengirim untuk mengecek identitas.
    """
    teks = pesan_masuk.strip() # Jangan di lower dulu jika itu adalah Nama orang
    
    # 1. CEK IDENTITAS PENGGUNA
    # Jika nomor belum ada di database atau belum punya nama
    if nomor_pengirim not in USERS_DB:
        # Inisialisasi user baru dengan status 'menunggu_nama'
        USERS_DB[nomor_pengirim] = {'nama': None, 'status': 'menunggu_nama'}
        save_users()
        return "Halo! Selamat datang di Asisten Kesehatan.\nSebelum kita mulai, bolehkah saya tahu siapa nama panggilan Anda?"

    user_data = USERS_DB[nomor_pengirim]

    # 2. PROSES PENYIMPANAN NAMA (Jika statusnya masih menunggu_nama)
    if user_data.get('status') == 'menunggu_nama':
        nama_baru = teks  # Pesan yang masuk dianggap sebagai nama
        USERS_DB[nomor_pengirim]['nama'] = nama_baru
        USERS_DB[nomor_pengirim]['status'] = 'registered' # Ubah status jadi terdaftar
        save_users()
        return (f"Salam kenal, {nama_baru}! data Anda sudah saya simpan.\n\n"
                "Sekarang Anda bisa bertanya tentang:\n"
                "- Info [Nama Obat]\n"
                "- Tips kesehatan/penyakit")

    # Ambil nama user untuk percakapan selanjutnya
    nama_user = user_data['nama']
    teks_lower = teks.lower()

    # 3. LOGIKA CHATBOT NORMAL (Sudah kenal)
    if teks_lower in ['halo', 'hi', 'menu', 'pagi', 'siang', 'malam']:
        return (
            f"Halo {nama_user}! 👋 Senang bertemu Anda kembali.\n\n"
            "Ketik pertanyaan Anda, misalnya:\n"
            "➡️ Info Paracetamol\n"
            "➡️ Cara mengatasi flu tanpa obat"
        )
    
    # Fitur Ganti Nama (Opsional)
    if teks_lower == 'ganti nama':
        USERS_DB[nomor_pengirim]['status'] = 'menunggu_nama'
        save_users()
        return "Oke, silakan ketik nama baru Anda:"

    # Cek Database Lokal
    if teks_lower.startswith('info'):
        # Logika pencarian obat lokal (sama seperti sebelumnya)
        for obat in DATABASE_OBAT:
            for kata in obat['kata_kunci']:
                if kata in teks_lower:
                    return (f"Halo {nama_user}, berikut infonya:\n\n"
                            f"**{obat['nama_obat']}**\n"
                            f"Kegunaan: {obat['kegunaan_umum']}\n"
                            f"Peringatan: {obat['peringatan_keras']}")
    
    # Lempar ke Gemini jika tidak ada di database lokal
    print(f"User {nama_user} bertanya: {teks} -> Kirim ke Gemini")
    balasan = panggil_gemini(pesan_masuk, nama_user)
    return balasan

# WEBHOOK ENDPOINT 
@app.route('/webhook-fonnte', methods=['POST'])
def webhook_fonnte():
    try:
        data = request.json
        print(f"Debug Fonnte: {json.dumps(data, indent=2)}")
        
        pesan_masuk = data.get('message')
        nomor_pengirim = data.get('sender')
        is_group = data.get('isGroup', False)
        
        if pesan_masuk and nomor_pengirim and not is_group:
            # Kita kirim nomor_pengirim juga ke fungsi proses_pesan
            teks_balasan = proses_pesan(pesan_masuk, nomor_pengirim)
            kirim_balasan_fonnte(nomor_pengirim, teks_balasan)
            
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"ERROR webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Jalankan Server 
if __name__ == '__main__':
    load_database_obat()
    load_users() # Load data user saat server nyala
    print("Server chatbot berjalan...")
    app.run(debug=True, port=5000)
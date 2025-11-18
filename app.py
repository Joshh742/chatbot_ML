# app.py
from flask import Flask, request, jsonify
import requests
import json
import re
import os
import google.generativeai as genai
from dotenv import load_dotenv

app = Flask(__name__)

# --- 1. Muat API Key dari file .env ---
load_dotenv()
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not FONNTE_TOKEN or not GEMINI_API_KEY:
    print("FATAL ERROR: Pastikan FONNTE_TOKEN dan GEMINI_API_KEY ada di file .env Anda!")

# --- 2. Konfigurasi Model Gemini ---
# PENTING: Nama variabelnya 'model' (bukan 'gemini_model')
# PENTING: Nama modelnya 'gemini-1.5-flash-latest' (tanpa 'models/')
model = None 
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("Koneksi ke Gemini API berhasil.")
except Exception as e:
    print(f"ERROR FATAL SAAT STARTUP: Gagal konfigurasi Gemini: {e}")
    print("Model AI TIDAK AKAN berfungsi.")

# --- 3. Variabel Global & Fungsi Pembantu ---
DATABASE_OBAT = []

def load_database_obat():
    global DATABASE_OBAT
    try:
        with open('database_obat.json', 'r', encoding='utf-8') as f:
            DATABASE_OBAT = json.load(f)
        print(f"Berhasil memuat {len(DATABASE_OBAT)} data obat dari JSON.")
    except Exception as e:
        print(f"ERROR: Gagal memuat database_obat.json: {e}")

def kirim_balasan_fonnte(nomor_tujuan, teks_balasan):
    url_api_fonnte = "https://api.fonnte.com/send"
    headers = {"Authorization": FONNTE_TOKEN}
    payload = {"target": nomor_tujuan, "message": teks_balasan}
    
    try:
        response = requests.post(url_api_fonnte, headers=headers, data=payload)
        response.raise_for_status() 
        print(f"Berhasil mengirim balasan ke {nomor_tujuan}")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Gagal mengirim balasan ke Fonnte: {e}")

def panggil_gemini(pertanyaan):
    """
    Mengirim pertanyaan ke Gemini API dengan instruksi TUGAS KAMPUS.
    """
    if model is None:
        print("ERROR: panggil_gemini dipanggil tapi model=None.")
        return "Maaf, AI sedang mengalami gangguan (Model Load Error). Periksa log server."

    instruksi_tugas = (
        "Anda adalah asisten kesehatan AI untuk tugas kampus. "
        "Peran Anda adalah menjawab pertanyaan pengguna tentang kesehatan. "
        "Ketika pengguna bertanya tentang 'obat apa' dan 'pola hidup apa' untuk suatu penyakit (misal: 'demam'), "
        "Anda BOLEH memberikan jawaban yang informatif. "
        "Sebutkan obat bebas (OTC) yang umum (seperti Paracetamol untuk demam) DAN pola hidup yang disarankan. "
        "SELALU akhiri jawaban Anda dengan peringatan bahwa Anda adalah AI dan jawaban ini tidak menggantikan nasihat dokter profesional. "
        "Jawab dalam bahasa Indonesia yang ringkas dan jelas untuk WhatsApp."
    )

    try:
        # PENTING: Nama variabelnya 'model' (bukan 'gemini_model')
        response = model.generate_content(f"{instruksi_tugas}\n\nPertanyaan Pengguna: {pertanyaan}")
        return response.text
    except Exception as e:
        print(f"ERROR: Gagal memanggil Gemini API: {e}")
        # Jika error v1beta muncul lagi, berarti library masih lama
        return "Maaf, AI sedang mengalami gangguan (API Call Error). Silakan coba lagi nanti." 

# --- 4. OTAK UTAMA BOT (LOGIKA HIBRIDA) ---
def proses_pesan(pesan_masuk):
    teks = pesan_masuk.lower().strip()
    balasan = ""

    if teks in ['halo', 'hi', 'menu', 'pagi']:
        balasan = (
            "Halo! 👋 Selamat datang di Asisten Kesehatan (Versi Tugas Kampus).\n\n"
            "**DISCLAIMER:** Saya adalah AI untuk demo. Informasi ini mungkin tidak akurat dan tidak menggantikan nasihat medis profesional.\n\n"
            "Silakan ketik pertanyaan Anda:\n"
            "➡️ *Info [Nama Obat]* (Contoh: Info Paracetamol)\n"
            "➡️ *Obat untuk demam dan pola hidupnya*"
        )
        return balasan

    if teks.startswith('info'):
        ditemukan = False
        for obat in DATABASE_OBAT:
            for kata in obat['kata_kunci']:
                if kata in teks:
                    balasan = (
                        f"Menampilkan informasi untuk: **{obat['nama_obat']}**\n\n"
                        f"**Kegunaan Umum:**\n{obat['kegunaan_umum']}\n\n"
                        f"**PERINGATAN KERAS:**\n{obat['peringatan_keras']}"
                    )
                    ditemukan = True
                    break
            if ditemukan: break
        
        if ditemukan:
            return balasan
        else:
            print(f"Obat '{teks}' tidak ada di JSON, melempar ke Gemini...")
            balasan = panggil_gemini(pesan_masuk)
            return balasan

    print(f"Tidak ada aturan lokal, melempar '{teks}' ke Gemini...")
    balasan = panggil_gemini(pesan_masuk)
    
    return balasan

# --- 5. WEBHOOK ENDPOINT (PINTU MASUK FONNTE) ---
@app.route('/webhook-fonnte', methods=['POST'])
def webhook_fonnte():
    try:
        data = request.json
        print(f"Menerima data dari Fonnte: {json.dumps(data, indent=2)}")
        pesan_masuk = data.get('message')
        nomor_pengirim = data.get('sender')
        is_group = data.get('isGroup', False)
        if pesan_masuk and nomor_pengirim and not is_group:
            teks_balasan = proses_pesan(pesan_masuk)
            kirim_balasan_fonnte(nomor_pengirim, teks_balasan)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"ERROR memproses webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- 6. Jalankan Server Flask ---
if __name__ == '__main__':
    load_database_obat()
    print("Server chatbot Flask (Versi Tugas Kampus - PERMISIF) berjalan di port 5000...")
    app.run(debug=True, port=5000)
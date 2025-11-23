# =============================
# KARTU PERSEDIAAN METODE FIFO (First In First Out)
# =============================

import streamlit as st
import pandas as pd
from datetime import date
import os
from io import BytesIO
import json

USER_FILE = "users.json"
DATA_FOLDER = "data_persediaan"

# ---------------- LOGIN SYSTEM ----------------

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USER_FILE, "w") as f:
        json.dump(users, f, indent=4)

# ---------------- LOGIN PAGE ----------------

ddef login_page():
    st.title("🔐 Login Kartu Persediaan")
    tab_login, tab_register, tab_forgot = st.tabs(["Login", "Register", "Lupa Password"])
    users = load_users()

    # ------------ LOGIN ------------
    with tab_login:
        st.subheader("Masuk ke Akun Anda")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        login_btn = st.button("Login", key="login_btn")

        if login_btn:
            if email in users and users[email]["password"] == password:
                st.session_state["login"] = True
                st.session_state["user"] = email
                st.success("✅ Login berhasil")
                st.rerun()
            else:
                st.error("❌ Email atau password salah")

    # ------------ REGISTER ------------
    with tab_register:
        st.subheader("Buat Akun Baru")
        reg_email = st.text_input("Email Baru", key="reg_email")
        reg_pass = st.text_input("Password Baru", type="password", key="reg_pass")
        reg_btn = st.button("Register", key="reg_btn")

        if reg_btn:
            if reg_email in users:
                st.warning("Email sudah terdaftar")
            else:
                users[reg_email] = {"password": reg_pass}
                save_users(users)
                st.success("✅ Akun berhasil dibuat, silakan login")

    # ------------ LUPA PASSWORD ------------
    with tab_forgot:
        st.subheader("Reset Password")
        forgot_email = st.text_input("Masukkan Email Terdaftar", key="forgot_email")
        new_pass = st.text_input("Password Baru", type="password", key="forgot_password")
        reset_btn = st.button("Reset Password", key="reset_btn")

        if reset_btn:
            if forgot_email in users:
                users[forgot_email]["password"] = new_pass
                save_users(users)
                st.success("✅ Password berhasil direset")
            else:
                st.error("Email tidak ditemukan")
                
# ---------------- APLIKASI FIFO ----------------

def main_app():
    st.sidebar.title(f"👤 {st.session_state['user']}")
    if st.sidebar.button("🚪 Logout"):
        st.session_state.clear()
        st.rerun()

    st.title("📦 Kartu Persediaan - Metode FIFO")

    def load_data():
        data = {}
        if os.path.exists(DATA_FOLDER):
            for file in os.listdir(DATA_FOLDER):
                if file.endswith('.csv'):
                    data[file.replace('.csv','')] = pd.read_csv(os.path.join(DATA_FOLDER,file))
        return data

    def save_data():
        os.makedirs(DATA_FOLDER, exist_ok=True)
        for nama, df in st.session_state["persediaan"].items():
            df.to_csv(os.path.join(DATA_FOLDER, f"{nama}.csv"), index=False)

    if "persediaan" not in st.session_state:
        st.session_state["persediaan"] = load_data()

    nama_barang = st.sidebar.text_input("Nama Barang Baru")
    if st.sidebar.button("Tambah Barang") and nama_barang:
        st.session_state["persediaan"][nama_barang] = pd.DataFrame(columns=[
            "Tanggal", "Keterangan", "Masuk Qty", "Harga Masuk",
            "Keluar Qty", "Harga Keluar", "Saldo Qty", "Saldo Nilai"
        ])

    if not st.session_state["persediaan"]:
        st.info("Tambahkan barang terlebih dahulu")
        st.stop()

    pilihan_barang = st.sidebar.selectbox("Pilih Barang", list(st.session_state["persediaan"].keys()))

    df = st.session_state["persediaan"][pilihan_barang]

    st.subheader(f"Input Transaksi FIFO - {pilihan_barang}")
    jenis = st.selectbox("Jenis", ["Pembelian", "Penjualan"])
    tanggal = st.date_input("Tanggal", date.today())
    qty = st.number_input("Jumlah", min_value=1, step=1)
    harga = st.number_input("Harga per Unit", min_value=0.0, step=100.0)

    if st.button("Simpan"):
        saldo_qty = df["Saldo Qty"].iloc[-1] if len(df)>0 else 0
        saldo_nilai = df["Saldo Nilai"].iloc[-1] if len(df)>0 else 0

        if jenis == "Pembelian":
            saldo_qty += qty
            saldo_nilai += qty * harga

        else:
            if qty > saldo_qty:
                st.error("Stok tidak cukup")
                st.stop()
            saldo_qty -= qty
            saldo_nilai -= qty * harga

        new_row = {
            "Tanggal": tanggal,
            "Keterangan": jenis,
            "Masuk Qty": qty if jenis=="Pembelian" else 0,
            "Harga Masuk": harga if jenis=="Pembelian" else 0,
            "Keluar Qty": qty if jenis=="Penjualan" else 0,
            "Harga Keluar": harga if jenis=="Penjualan" else 0,
            "Saldo Qty": saldo_qty,
            "Saldo Nilai": saldo_nilai
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        st.session_state["persediaan"][pilihan_barang] = df
        save_data()
        st.success("Transaksi tersimpan")

    st.dataframe(df, use_container_width=True)

    # HAPUS TRANSAKSI
    if len(df) > 0:
        index_hapus = st.number_input("Nomor baris transaksi yang mau dihapus", min_value=0, max_value=len(df)-1, step=1)
        if st.button("🗑️ Hapus Transaksi"):
            df = df.drop(index=index_hapus).reset_index(drop=True)
            st.session_state["persediaan"][pilihan_barang] = df
            save_data()
            st.success("Transaksi dihapus")
            st.rerun()

    # EXPORT EXCEL
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=pilihan_barang)

    st.download_button(
        label="📥 Download Excel",
        data=buffer.getvalue(),
        file_name=f"Kartu_Persediaan_{pilihan_barang}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ---------------- RUN ----------------
if "login" not in st.session_state:
    st.session_state["login"] = False

if st.session_state["login"]:
    main_app()
else:
    login_page()
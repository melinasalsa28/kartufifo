# =============================
# KARTU PERSEDIAAN METODE FIFO (AKUNTANSI SEBENARNYA)
# + LAPORAN PERSEDIAAN
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

def login_page():
    st.title("🔐 Login Kartu Persediaan FIFO")
    tab_login, tab_register, tab_forgot = st.tabs(["Login", "Register", "Lupa Password"])
    users = load_users()

    with tab_login:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if email in users and users[email]["password"] == password:
                st.session_state["login"] = True
                st.session_state["user"] = email
                st.success("Login berhasil")
                st.rerun()
            else:
                st.error("Email atau password salah")

    with tab_register:
        reg_email = st.text_input("Email Baru")
        reg_pass = st.text_input("Password Baru", type="password")
        if st.button("Register"):
            users[reg_email] = {"password": reg_pass}
            save_users(users)
            st.success("Akun berhasil dibuat")

    with tab_forgot:
        forgot_email = st.text_input("Email Terdaftar")
        new_pass = st.text_input("Password Baru", type="password")
        if st.button("Reset Password"):
            if forgot_email in users:
                users[forgot_email]["password"] = new_pass
                save_users(users)
                st.success("Password berhasil direset")
            else:
                st.error("Email tidak ditemukan")

# ---------------- APLIKASI FIFO ----------------

def main_app():
    st.sidebar.title(f"👤 {st.session_state['user']}")
    if st.sidebar.button("🚪 Logout"):
        st.session_state.clear()
        st.rerun()

    st.title("📦 Kartu Persediaan FIFO (Akuntansi)")

    def load_data():
        data = {}
        if os.path.exists(DATA_FOLDER):
            for file in os.listdir(DATA_FOLDER):
                if file.endswith(".csv"):
                    nama = file.replace(".csv","")
                    data[nama] = pd.read_csv(os.path.join(DATA_FOLDER, file))
        return data

    def save_data():
        os.makedirs(DATA_FOLDER, exist_ok=True)
        for nama, df in st.session_state.persediaan.items():
            df.to_csv(os.path.join(DATA_FOLDER, f"{nama}.csv"), index=False)

    if "persediaan" not in st.session_state:
        st.session_state.persediaan = load_data()

    # -------- TAMBAH BARANG --------
    nama_barang = st.sidebar.text_input("Nama Barang Baru")
    if st.sidebar.button("Tambah Barang") and nama_barang:
        st.session_state.persediaan[nama_barang] = pd.DataFrame(columns=[
            "Tanggal", "Keterangan", "Masuk Qty", "Harga Masuk",
            "Keluar Qty", "HPP FIFO", "Saldo Qty", "Saldo Nilai"
        ])

    if not st.session_state.persediaan:
        st.info("Tambahkan barang dulu")
        st.stop()

    barang = st.sidebar.selectbox("Pilih Barang", list(st.session_state.persediaan.keys()))
    df = st.session_state.persediaan[barang]

    st.subheader(f"Input Transaksi FIFO - {barang}")
    jenis = st.selectbox("Jenis Transaksi", ["Pembelian", "Penjualan"])
    tanggal = st.date_input("Tanggal", date.today())
    qty = st.number_input("Jumlah", min_value=1, step=1)
    harga = st.number_input("Harga per Unit", min_value=0.0)

    # ---------------- FIFO ENGINE ----------------
    if st.button("Simpan"):
        saldo_qty = df["Saldo Qty"].iloc[-1] if len(df)>0 else 0
        saldo_nilai = df["Saldo Nilai"].iloc[-1] if len(df)>0 else 0

        if jenis == "Pembelian":
            saldo_qty += qty
            saldo_nilai += qty * harga
            hpp = 0

        else:
            if qty > saldo_qty:
                st.error("Stok tidak mencukupi")
                st.stop()

            qty_keluar = qty
            total_hpp = 0

            temp_df = df.copy()
            for i, row in temp_df.iterrows():
                sisa = row["Masuk Qty"] - row["Keluar Qty"]
                if sisa <= 0:
                    continue
                ambil = min(sisa, qty_keluar)
                total_hpp += ambil * row["Harga Masuk"]
                qty_keluar -= ambil
                temp_df.at[i, "Keluar Qty"] += ambil
                if qty_keluar == 0:
                    break

            df.update(temp_df)
            saldo_qty -= qty
            saldo_nilai -= total_hpp
            hpp = total_hpp

        new_row = {
            "Tanggal": tanggal,
            "Keterangan": jenis,
            "Masuk Qty": qty if jenis=="Pembelian" else 0,
            "Harga Masuk": harga if jenis=="Pembelian" else 0,
            "Keluar Qty": qty if jenis=="Penjualan" else 0,
            "HPP FIFO": hpp,
            "Saldo Qty": saldo_qty,
            "Saldo Nilai": saldo_nilai
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        st.session_state.persediaan[barang] = df
        save_data()
        st.success("Transaksi FIFO tersimpan")

    st.dataframe(df, use_container_width=True)

    # ---------------- LAPORAN ----------------
    st.subheader("📊 Laporan Persediaan")
    total_masuk = df["Masuk Qty"].sum()
    total_keluar = df["Keluar Qty"].sum()
    saldo_akhir_qty = df["Saldo Qty"].iloc[-1] if len(df)>0 else 0
    saldo_akhir_nilai = df["Saldo Nilai"].iloc[-1] if len(df)>0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Masuk", total_masuk)
    col2.metric("Total Keluar", total_keluar)
    col3.metric("Saldo Qty", saldo_akhir_qty)
    col4.metric("Saldo Nilai", f"Rp {saldo_akhir_nilai:,.0f}")

    # ---------------- EXPORT EXCEL ----------------
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=barang)

    st.download_button(
        "📥 Download Excel FIFO",
        data=buffer.getvalue(),
        file_name=f"FIFO_{barang}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ---------------- RUN APP ----------------
if "login" not in st.session_state:
    st.session_state["login"] = False

if st.session_state["login"]:
    main_app()
else:
    login_page()

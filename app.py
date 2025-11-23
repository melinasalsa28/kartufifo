
import streamlit as st
import pandas as pd
from datetime import date
import os
import json
from io import BytesIO

USER_FILE = "users.json"
DATA_FOLDER = "data_persediaan"

# ---------------- Helpers ----------------

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, "r") as f:
            return json.load(f)
    return {}


def save_users(users):
    with open(USER_FILE, "w") as f:
        json.dump(users, f, indent=4)


def ensure_data_folder():
    os.makedirs(DATA_FOLDER, exist_ok=True)


def load_all_data():
    ensure_data_folder()
    data = {}
    for fn in os.listdir(DATA_FOLDER):
        if fn.endswith('.csv'):
            name = fn[:-4]
            df = pd.read_csv(os.path.join(DATA_FOLDER, fn))
            data[name] = df
    return data


def save_all_data(data_dict):
    ensure_data_folder()
    for name, df in data_dict.items():
        df.to_csv(os.path.join(DATA_FOLDER, f"{name}.csv"), index=False)


# ---------------- FIFO Engine Functions ----------------

def compute_current_saldo(df):
    if df is None or df.empty:
        return 0, 0.0
    last = df.iloc[-1]
    return int(last.get('Saldo Qty', 0)), float(last.get('Saldo Nilai', 0.0))


def apply_purchase(df, tanggal, qty, unit_price):
    # Append a purchase row (Masuk Qty)
    saldo_qty, saldo_nilai = compute_current_saldo(df)
    saldo_qty += qty
    saldo_nilai += qty * unit_price
    new_row = {
        'Tanggal': pd.to_datetime(tanggal).date(),
        'Keterangan': 'Pembelian',
        'Masuk Qty': int(qty),
        'Harga Masuk': float(unit_price),
        'Keluar Qty': 0,
        'HPP': 0.0,
        'Saldo Qty': int(saldo_qty),
        'Saldo Nilai': float(saldo_nilai)
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    return df


def apply_sale_fifo(df, tanggal, qty):
    # Sell qty using FIFO, consume previous purchase batches
    saldo_qty, saldo_nilai = compute_current_saldo(df)
    if qty > saldo_qty:
        raise ValueError('Stok tidak cukup')

    qty_to_consume = qty
    total_hpp = 0.0

    # Work on a copy of rows to update Keluar Qty on purchase rows
    if df is None:
        df = pd.DataFrame()
    temp = df.copy()
    # Ensure numeric types
    for col in ['Masuk Qty', 'Harga Masuk', 'Keluar Qty']:
        if col not in temp.columns:
            temp[col] = 0

    # Iterate from top (oldest rows) consuming available Masuk - Keluar
    for idx, row in temp.iterrows():
        if qty_to_consume <= 0:
            break
        masuk = int(row.get('Masuk Qty', 0))
        keluar = int(row.get('Keluar Qty', 0))
        available = masuk - keluar
        if available <= 0:
            continue
        take = min(available, qty_to_consume)
        price = float(row.get('Harga Masuk', 0.0))
        total_hpp += take * price
        temp.at[idx, 'Keluar Qty'] = keluar + take
        qty_to_consume -= take

    # After consumption, update saldo
    saldo_qty -= qty
    saldo_nilai -= total_hpp

    # Update HPP on this sale row
    new_row = {
        'Tanggal': pd.to_datetime(tanggal).date(),
        'Keterangan': 'Penjualan',
        'Masuk Qty': 0,
        'Harga Masuk': 0.0,
        'Keluar Qty': int(qty),
        'HPP': float(total_hpp),
        'Saldo Qty': int(saldo_qty),
        'Saldo Nilai': float(saldo_nilai)
    }

    # Merge temp back: keep temp rows (with updated Keluar Qty), then append new sale row
    df = temp.copy()
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    return df


def apply_retur_penjualan(df, tanggal, qty):
    # Customer returns items -> add back to stock at HPP per consumed layers (we will add back at weighted HPP)
    # Simpler approach: determine average HPP of last sales consumed layers
    # We will approximate by adding back at unit cost = (total HPP of latest sales / qty_from_sales) if available
    # For simplicity, add back at unit cost = (total HPP / sold qty) from newest sales rows
    # Find recent sale rows and compute HPP per unit
    if df is None or df.empty:
        # nothing to return to
        unit_price = 0.0
    else:
        # Find last sale rows and sum until qty covered
        needed = qty
        total_val = 0.0
        # iterate rows in reverse (from latest) to earlier
        for idx in range(len(df)-1, -1, -1):
            row = df.iloc[idx]
            if row.get('Keterangan') != 'Penjualan':
                continue
            sold = int(row.get('Keluar Qty', 0))
            hpp = float(row.get('HPP', 0.0))
            if sold <= 0:
                continue
            take = min(needed, sold)
            per_unit = hpp / sold if sold>0 else 0
            total_val += take * per_unit
            needed -= take
            if needed==0:
                break
        unit_price = (total_val / qty) if qty>0 else 0.0

    # Apply as a purchase (masuk) with unit_price
    df = apply_purchase(df, tanggal, qty, unit_price)
    # Mark keterangan as Retur Penjualan on appended row
    df.at[len(df)-1, 'Keterangan'] = 'Retur Penjualan'
    return df


def apply_retur_pembelian(df, tanggal, qty):
    # Return to supplier: remove stock using FIFO (same as sale but mark keterangan Retur Pembelian)
    df = apply_sale_fifo(df, tanggal, qty)
    df.at[len(df)-1, 'Keterangan'] = 'Retur Pembelian'
    return df


# ---------------- App UI ----------------

def login_page():
    st.title("🔐 Login Kartu Persediaan FIFO")
    tab_login, tab_register, tab_forgot = st.tabs(["Login", "Register", "Lupa Password"])
    users = load_users()

    # LOGIN
    with tab_login:
        st.subheader("Masuk ke Akun Anda")
        email = st.text_input("Email", key='login_email')
        password = st.text_input("Password", type='password', key='login_password')
        if st.button('Login', key='btn_login'):
            if email in users and users[email]['password'] == password:
                st.session_state['login'] = True
                st.session_state['user'] = email
                st.success('Login berhasil')
                st.rerun()
            else:
                st.error('Email atau password salah')

    # REGISTER
    with tab_register:
        st.subheader('Buat Akun Baru')
        reg_email = st.text_input('Email Baru', key='reg_email')
        reg_pass = st.text_input('Password Baru', type='password', key='reg_pass')
        if st.button('Register', key='btn_register'):
            if reg_email in users:
                st.warning('Email sudah terdaftar')
            else:
                users[reg_email] = {'password': reg_pass}
                save_users(users)
                st.success('Akun berhasil dibuat. Silakan login')

    # LUPA PASSWORD
    with tab_forgot:
        st.subheader('Reset Password')
        forgot_email = st.text_input('Masukkan Email Terdaftar', key='forgot_email')
        new_pass = st.text_input('Password Baru', type='password', key='forgot_password')
        if st.button('Reset Password', key='btn_reset'):
            if forgot_email in users:
                users[forgot_email]['password'] = new_pass
                save_users(users)
                st.success('Password berhasil direset')
            else:
                st.error('Email tidak ditemukan')


def main_app():
    st.sidebar.title(f"👤 {st.session_state.get('user','-')}")
    if st.sidebar.button('🚪 Logout', key='btn_logout'):
        st.session_state.clear()
        st.rerun()

    # Load data into session
    if 'persediaan' not in st.session_state:
        st.session_state['persediaan'] = load_all_data()

    st.title('📦 Kartu Persediaan - FIFO Akuntansi (Real)')

    # Add new product + set opening balance
    st.sidebar.subheader('Master Barang & Saldo Awal')
    nama_baru = st.sidebar.text_input('Nama Barang Baru', key='new_item_name')
    opening_qty = st.sidebar.number_input('Saldo Awal Qty', min_value=0, step=1, key='opening_qty')
    opening_price = st.sidebar.number_input('Harga per Unit Saldo Awal', min_value=0.0, step=100.0, key='opening_price')
    if st.sidebar.button('Tambah Barang & Set Saldo Awal', key='btn_add_item') and nama_baru:
        if nama_baru in st.session_state['persediaan']:
            st.sidebar.warning('Barang sudah ada')
        else:
            # create dataframe and append opening batch if >0
            cols = ['Tanggal','Keterangan','Masuk Qty','Harga Masuk','Keluar Qty','HPP','Saldo Qty','Saldo Nilai']
            df = pd.DataFrame(columns=cols)
            if opening_qty > 0:
                df = apply_purchase(df, date.today(), int(opening_qty), float(opening_price))
                df.at[len(df)-1,'Keterangan'] = 'Saldo Awal'
            st.session_state['persediaan'][nama_baru] = df
            save_all_data(st.session_state['persediaan'])
            st.sidebar.success('Barang & saldo awal tersimpan')

    # list products
    products = list(st.session_state['persediaan'].keys())
    if not products:
        st.info('Belum ada barang. Tambahkan barang di sidebar.')
        return

    produk = st.sidebar.selectbox('Pilih Barang', products, key='select_product')
    df = st.session_state['persediaan'].get(produk, pd.DataFrame())

    # Transaction area
    st.subheader(f'Transaksi - {produk}')
    jenis = st.selectbox('Jenis Transaksi', ['Pembelian','Penjualan','Retur Penjualan','Retur Pembelian'], key='trans_type')
    tgl = st.date_input('Tanggal', value=date.today(), key='trans_date')
    qty = st.number_input('Jumlah', min_value=0, step=1, key='trans_qty')
    price = st.number_input('Harga per Unit (untuk pembelian atau retur pembelian)', min_value=0.0, step=100.0, key='trans_price')

    if st.button('Simpan Transaksi', key='btn_save_trans'):
        try:
            if jenis == 'Pembelian':
                df = apply_purchase(df, tgl, int(qty), float(price))
            elif jenis == 'Penjualan':
                if qty<=0:
                    st.warning('Jumlah harus > 0')
                else:
                    df = apply_sale_fifo(df, tgl, int(qty))
            elif jenis == 'Retur Penjualan':
                if qty<=0:
                    st.warning('Jumlah harus > 0')
                else:
                    df = apply_retur_penjualan(df, tgl, int(qty))
            elif jenis == 'Retur Pembelian':
                if qty<=0:
                    st.warning('Jumlah harus > 0')
                else:
                    # For retur pembelian, we remove stock based on FIFO consumption
                    df = apply_retur_pembelian(df, tgl, int(qty))

            st.session_state['persediaan'][produk] = df
            save_all_data(st.session_state['persediaan'])
            st.success('Transaksi tersimpan')
        except ValueError as e:
            st.error(str(e))

    st.divider()

    # Display transactions
    if df is None or df.empty:
        st.info('Belum ada transaksi untuk produk ini')
    else:
        st.subheader('Kartu Persediaan (Detail)')
        st.dataframe(df, use_container_width=True)

        # Delete transaction
        idx_to_delete = st.number_input('Nomor baris yang ingin dihapus', min_value=0, max_value=len(df)-1, step=1, key='del_index')
        if st.button('Hapus Baris', key='btn_delete'):
            df = df.drop(index=int(idx_to_delete)).reset_index(drop=True)
            # After deleting a row we should recompute saldo and Keluar Qty appropriately - simple approach: recompute full history
            df = recompute_from_transactions(df)
            st.session_state['persediaan'][produk] = df
            save_all_data(st.session_state['persediaan'])
            st.success('Baris dihapus dan saldo direkalkulasi')

    st.divider()

    # Report
    st.subheader('Laporan Persediaan')
    total_masuk = int(df['Masuk Qty'].sum()) if 'Masuk Qty' in df.columns else 0
    total_keluar = int(df['Keluar Qty'].sum()) if 'Keluar Qty' in df.columns else 0
    saldo_qty, saldo_nilai = compute_current_saldo(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Total Masuk', f"{total_masuk}")
    c2.metric('Total Keluar', f"{total_keluar}")
    c3.metric('Saldo Qty', f"{saldo_qty}")
    c4.metric('Saldo Nilai', f"Rp {saldo_nilai:,.0f}")

    # Export Excel
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        if df is not None:
            df.to_excel(writer, index=False, sheet_name=produk)
    st.download_button('📥 Download Excel FIFO', data=buffer.getvalue(), file_name=f'FIFO_{produk}.xlsx', mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', key='btn_download')


# ---------------- Utility to recompute full history ----------------

def recompute_from_transactions(df_raw):
    # Given a dataframe where rows may be mixed (some purchases, some sales, etc), recompute Keluar Qty per batch and saldo sequentially
    cols = ['Tanggal','Keterangan','Masuk Qty','Harga Masuk','Keluar Qty','HPP','Saldo Qty','Saldo Nilai']
    df_clean = pd.DataFrame(columns=cols)

    # We'll interpret rows that have Masuk Qty>0 as purchase batches. For sales rows, we will consume FIFO from earlier batches.
    for _, row in df_raw.iterrows():
        k = row.get('Keterangan','')
        m = int(row.get('Masuk Qty', 0))
        p = float(row.get('Harga Masuk', 0.0))
        kq = int(row.get('Keluar Qty', 0))
        tgl = row.get('Tanggal', pd.to_datetime('today').date())

        if m>0 and (k=='' or k=='Pembelian' or k=='Saldo Awal' or k=='Retur Penjualan'):
            # treat as purchase
            df_clean = apply_purchase(df_clean, tgl, m, p)
            df_clean.at[len(df_clean)-1,'Keterangan'] = row.get('Keterangan', 'Pembelian')
        elif kq>0 or k=='Penjualan' or k=='Retur Pembelian':
            # treat as sale/consumption
            df_clean = apply_sale_fifo(df_clean, tgl, kq)
            df_clean.at[len(df_clean)-1,'Keterangan'] = row.get('Keterangan','Penjualan')
        else:
            # ignore unknown row
            pass
    return df_clean


# ---------------- Run ----------------
if 'login' not in st.session_state:
    st.session_state['login'] = False

if st.session_state['login']:
    main_app()
else:
    login_page()

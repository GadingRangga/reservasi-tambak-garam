FROM python:3.11-slim

WORKDIR /app

# Mencegah Python membuat file .pyc dan memastikan log langsung tampil di terminal
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Layer 1 (Dependency): dipisah dari source code agar dapat di-cache saat hanya kode app/ berubah
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2 (Kode Aplikasi): hanya layer ini yang dibangun ulang pada skenario perubahan kode
COPY app/ ./app/

EXPOSE 5000

# --preload memastikan inisialisasi tabel DB berjalan sekali sebelum 2 worker Gunicorn aktif
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--preload", "app.main:app"]
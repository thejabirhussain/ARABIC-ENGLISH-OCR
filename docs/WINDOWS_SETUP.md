# Windows Installation & Setup Guide

This guide provides step-by-step instructions for setting up the Arabic-English OCR application on Windows 10/11.

## 1. Install System Dependencies

Unlike macOS, Windows does not have a single package manager like Homebrew for all these tools. You will need to download and install them manually or use `winget`/`choco`.

### A. Install Python & Node.js
1.  **Python 3.10+**: Download from [python.org](https://www.python.org/downloads/).
    *   **Important:** Check the box **"Add Python to PATH"** during installation.
2.  **Node.js (LTS)**: Download from [nodejs.org](https://nodejs.org/).

### B. Install Tesseract OCR
1.  Download the Windows installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
2.  Run the installer.
3.  **Important:** During installation, looks for "Additional Script Data" or "Language Data" and make sure **Arabic** script/language is selected.
4.  Add the installation path (usually `C:\Program Files\Tesseract-OCR`) to your **System PATH**.
    *   Search "Edit the system environment variables" -> Environment Variables -> Path -> Edit -> New.

### C. Install Poppler (for PDF processing)
1.  Download the latest Release binary from [github.com/oschwartz10612/poppler-windows/releases](https://github.com/oschwartz10612/poppler-windows/releases).
2.  Extract the ZIP file (e.g., to `C:\Program Files\poppler`).
3.  Add the `bin` folder path (e.g., `C:\Program Files\poppler\Library\bin`) to your **System PATH**.

### D. Install Ghostscript
1.  Download the installer from [ghostscript.com/releases/gsdnld.html](https://www.ghostscript.com/releases/gsdnld.html).
2.  Install it and add the `bin` folder to your **System PATH**.

---

## 2. Project Setup

Open **Command Prompt (cmd)** or **PowerShell** as Administrator for the first run to ensure permissions.

### Backend Setup

```powershell
# 1. Navigate to the backend folder
cd backend

# 2. Create a virtual environment
python -m venv venv

# 3. Activate the virtual environment
# For Command Prompt (cmd):
venv\Scripts\activate.bat
# For PowerShell:
.\venv\Scripts\Activate.ps1

# 4. Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Note: If you get an error installing 'sentencepiece' or others, 
# you might need "Microsoft C++ Build Tools" installed.
```

### Frontend Setup

```powershell
# 1. Navigate to the frontend folder
cd frontend

# 2. Install dependencies
npm install
```

---

## 3. Running the Application

You will need two separate terminal windows.

### Terminal 1: Backend

```powershell
cd backend
# Make sure venv is active (you should see (venv) in the prompt)
.\venv\Scripts\Activate.ps1
python main.py
```
*Server runs at `http://localhost:8000`*

### Terminal 2: Frontend

```powershell
cd frontend
npm run dev
```
*App runs at `http://localhost:5173`*

---

## Troubleshooting on Windows

*   **"Tesseract is not installed or it's not in your PATH"**:
    *   Restart your terminal after editing Environment Variables.
    *   Test by running `tesseract --version` in cmd.
*   **"Poppler error"**:
    *   Ensure the `bin` folder of Poppler is in your PATH.
    *   Test by running `pdftoppm -h`.
*   **Encoding Errors**:
    *   If you see strange characters in the terminal, run `chcp 65001` to enable UTF-8 support in Windows Console.

# Run the app locally (CPU): starts the backend and the frontend in two windows.
# Usage:  ./start.ps1     (from the repo root)
$root = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command",
  "cd '$root\backend'; `$env:PYTHONIOENCODING='utf-8'; .\venv\Scripts\python.exe -m uvicorn main:app --port 8000"

Start-Process powershell -ArgumentList "-NoExit", "-Command",
  "cd '$root\frontend'; npm run dev"

Write-Host ""
Write-Host "Backend  -> http://127.0.0.1:8000"
Write-Host "Frontend -> http://127.0.0.1:5173  (open this in your browser)"
Write-Host ""
Write-Host "First run only: in backend/ do 'py -3.11 -m venv venv; venv\Scripts\activate; pip install -r requirements.txt'"
Write-Host "and in frontend/ do 'npm install'. Put your key in backend/.env."

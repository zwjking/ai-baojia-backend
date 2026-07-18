Set-Location 'C:\Users\Administrator\.qclaw\shared\AI报价网后端'
$env:PYTHONUNBUFFERED='1'
$py = 'C:\Program Files\QClaw\v0.2.31.600\resources\python\python.exe'
Invoke-Expression "& '' -m uvicorn app.main:app --host 0.0.0.0 --port 8000"

# รันใน PowerShell ด้วย account Global Admin

Write-Host "Installing MicrosoftTeams module..." -ForegroundColor Cyan
Install-Module -Name MicrosoftTeams -Force -Scope CurrentUser -AllowClobber

Write-Host "Connecting to Microsoft Teams (จะมี popup ให้ login)..." -ForegroundColor Cyan
Connect-MicrosoftTeams

Write-Host "Creating application access policy..." -ForegroundColor Cyan
New-CsApplicationAccessPolicy `
    -Identity "TranscriptAccessPolicy" `
    -AppIds "927647b7-fc5a-47b9-817a-c037087b4e7f" `
    -Description "Allow app to read Teams meetings and transcripts"

Write-Host "Granting policy to all users in tenant..." -ForegroundColor Cyan
Grant-CsApplicationAccessPolicy `
    -PolicyName "TranscriptAccessPolicy" `
    -Global

Write-Host "Done! รอ 30-60 นาทีแล้วค่อยรัน python script" -ForegroundColor Green

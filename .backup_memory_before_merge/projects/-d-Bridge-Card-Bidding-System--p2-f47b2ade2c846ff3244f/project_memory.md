## Hard Constraints
- Python dependencies must be installed using the Microsoft Store channel to bypass sandbox restrictions on the official installer's Package Cache
- Node.js must be installed via 'MSI managed extraction' to a user directory (C:\Users\Yi_Fan\tools\node) and added to PATH, as official MSI requires administrator privileges
- PowerShell execution policy must be set to RemoteSigned to allow script execution
- The openai package version must be fixed to <2 to avoid compatibility issues with version 3

## Engineering Conventions
- requirements.txt must include all necessary dependencies: fastapi, uvicorn, python-dotenv, httpx, python-multipart, endplay

## Lessons Learned
- The 'trae solo' directory on D drive (D:\TRAE SOLO CN) only contains the software itself and no user history or configuration; user data is stored in C:\Users\Yi_Fan\.trae-cn\
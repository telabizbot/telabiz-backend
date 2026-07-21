from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import json
import httpx
import re
import jwt
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from cryptography.fernet import Fernet

load_dotenv()

app = FastAPI()

# CORS MUST BE FIRST
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Rest of your code ----------
# JWT and other imports continue...

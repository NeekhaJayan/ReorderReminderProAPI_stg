from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import models
from starlette.responses import RedirectResponse
from routers import auth
from starlette import status

app = FastAPI()
origins = [
    "*"
]
# Allow CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allow specific origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)
@app.get("/")
async def root():
    return RedirectResponse(url="/auth",status_code=status.HTTP_302_FOUND)

app.include_router(auth.router)

